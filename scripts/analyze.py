#!/usr/bin/env python3
"""Per-take checks: what a machine can honestly measure. Tone and acting stay with the human.

Measures sound level, clipping, head/tail room and pace, compares a local Whisper transcript with
the script, and estimates A/V offset from a clap. Whisper hides fillers, so they are never counted.
"""
import difflib
import json
import re
import subprocess
import tempfile
import threading
from pathlib import Path

RATE = 48000
QUIET_DB = -42.0  # below this, a 20 ms window counts as silence
WORKER = """
import json, sys, mlx_whisper
M = sys.argv[1]
for req in sys.stdin:
    lang, wav = req.strip().split(chr(9), 1)
    r = mlx_whisper.transcribe(wav, path_or_hf_repo=M, language=lang,
                               condition_on_previous_text=False, word_timestamps=False)
    print(json.dumps({"text": r["text"].strip()}), flush=True)
"""


class Whisper:
    """Keeps one process alive so each take does not reload the model."""

    def __init__(self, python, model="mlx-community/whisper-large-v3-turbo"):
        self.cmd = [python, "-c", WORKER, model]
        self.proc = None
        self.lock = threading.Lock()

    def transcribe(self, wav, lang="en"):
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.DEVNULL, text=True)
            self.proc.stdin.write(f"{lang}\t{wav}\n")
            self.proc.stdin.flush()
            out = self.proc.stdout.readline()
            if not out:
                raise RuntimeError("whisper worker stopped")
            return json.loads(out)["text"]


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def pcm(path):
    """Decode to 48 kHz mono float samples, without numpy, as a list of 20 ms peak levels in dB."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(RATE),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    import array
    import math
    s = array.array("h")
    s.frombytes(raw[: len(raw) // 2 * 2])
    win = RATE // 50
    levels = []
    for i in range(0, len(s), win):
        p = max((abs(v) for v in s[i: i + win]), default=0)
        levels.append(20 * math.log10(p / 32768) if p else -96.0)
    return levels, len(s) / RATE


def lufs(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(m[-1]) if m else None


ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "x x twenty thirty forty fifty sixty seventy eighty ninety".split()


def spell(n):
    """A transcript writes 12 or 2026 where the script spells the words out."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " hundred" + (" " + spell(n % 100) if n % 100 else "")
    if 2000 <= n < 3000 and n % 100:  # read as a year: twenty twenty-six
        return spell(n // 100) + " " + spell(n % 100)
    return str(n)


def words(text):
    text = re.sub(r"\d+", lambda m: spell(int(m.group())), text.lower().replace("’", "'"))
    return re.findall(r"[a-z0-9']+", text)


def plain(text):
    """Script text without its reading marks: *stress*, / pauses, {word|sounds like}."""
    text = re.sub(r"\{([^|}]+)\|[^}]*\}", r"\1", text)
    return re.sub(r"\s*/+\s*", " ", text.replace("*", "")).strip()


def spoken_key(text):
    """Letters read one by one (A I, U C) count as one word, as a transcript writes them."""
    return re.sub(r"\b([A-Z]) (?=[A-Z]\b)", r"\1", text)


def script_text(line):
    return spoken_key(plain((line or {}).get("t", "")))


def compare(script, heard):
    """Words in the script the transcript lacks, and words it adds. Names on the hard list are forgiven."""
    a, b = words(script), words(heard)
    missing, extra = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("delete", "replace"):
            missing += a[i1:i2]
        if op in ("insert", "replace"):
            extra += b[j1:j2]
    return missing, extra


GLOSS = re.compile(r"（[^）]*）")  # meaning of an English word, shown to reader and viewer, never spoken


def zh_chars(text):
    return re.sub(r"[^\u4e00-\u9fff]", "", GLOSS.sub("", text))


def zh_match(script, heard):
    """Share of the script's Chinese characters heard in order. Chinese transcripts often swap a character for one
    that sounds the same, so only a large gap means something was skipped. Latin names are left out."""
    a, b = zh_chars(script), zh_chars(heard)
    if not a:
        return 1.0
    return sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()) / len(a)


def analyze(path: Path, line, whisper=None):
    if path.stem.startswith("_clap"):
        return clap_report(path)
    levels, dur = pcm(path)
    speech = [i for i, v in enumerate(levels) if v > QUIET_DB]
    rep = {"ok": True, "duration": round(dur, 2), "notes": [], "info": [], "good": []}
    if not speech:
        rep.update(ok=False)
        rep["notes"].append("没录到声音，检查麦克风选择")
        return rep
    head, tail = speech[0] * .02, dur - (speech[-1] + 1) * .02
    peak = max(levels)
    span = (speech[-1] - speech[0] + 1) * .02
    loud = lufs(path)
    rep.update(head=round(head, 2), tail=round(tail, 2), peak=round(peak, 1), speech=round(span, 2), lufs=loud)

    if peak >= -1:
        rep["ok"] = False
        rep["notes"].append(f"削波了（峰值 {peak:.1f} dB）：退后一点，重录")
    elif peak < -32:  # only when post cannot raise it without bringing up the room noise too
        rep["ok"] = False
        rep["notes"].append(f"声音太小（峰值 {peak:.1f} dB）：检查是不是选错了麦克风")
    # Head and tail room are measured for the cut but never raised with the reader: silence is added in post.

    text = script_text(line)
    n = len(words(text))
    if n >= 4 and (line or {}).get("lang") != "zh":
        rate = n / span * 60
        rep["wpm"] = round(rate)
        rep["good"].append(f"语速约 {rate:.0f} 词/分")  # information only; pace is the reader's call
    if line and line.get("target"):
        rep["target"] = line["target"]
        rep["good"].append(f"这遍 {span:.0f} 秒，中文这段 {line['target']:.0f} 秒")  # information only

    if whisper and text:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "check.wav"
            run("ffmpeg", "-v", "error", "-y", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "16000", str(wav))
            heard = whisper.transcribe(wav, (line or {}).get("lang", "en"))
        if (line or {}).get("lang") == "zh":
            share = zh_match(text, heard)
            rep["heard"], rep["match"] = heard, round(share, 2)
            # A few changed words are the reader's call and never ask for another take; only a large gap is raised.
            if share < .5:
                rep["notes"].append(f"机器听写和稿子差得多，请回听：听到“{heard}”")
            elif share < .8:
                rep["info"].append("和稿子有几处不一样，意思对就不用重录")
            else:
                rep["good"].append("机器听写与稿子大致一致")
            return rep
        missing, extra = compare(text, heard)
        forgiven = set(words(" ".join(line.get("names", [])))) if line else set()
        misheard = sum(w in forgiven for w in missing)
        missing = [w for w in missing if w not in forgiven]
        extra = extra[misheard:]  # the transcript's spelling of a name is not an extra word
        rep["heard"] = heard
        rep["missing"], rep["extra"] = missing, extra
        if missing or extra:
            small = len(missing) + len(extra) <= max(2, round(n * .12))
            rep["info" if small else "notes"].append(("和稿子差几个词，意思对就不用重录：" if small else "机器听写和稿子不一样，请回听：") +
                                (f"没听到 {' '.join(missing)}" if missing else "") +
                                ("；" if missing and extra else "") +
                                (f"多出 {' '.join(extra)}" if extra else ""))
        else:
            rep["good"].append("机器听写与稿子一致")
    return rep


def clap_report(path: Path):
    """Offset of a clap: loudest sound against the moment the hands stop moving. Video timing is read from
    each frame's own timestamp, because a webcam's frame rate varies. Precision is about one frame."""
    levels, dur = pcm(path)
    t_audio = max(range(len(levels)), key=levels.__getitem__) * .02 + .01
    probe = json.loads(run("ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "frame=pts_time", "-of", "json", str(path)).stdout)
    pts = [float(f["pts_time"]) for f in probe["frames"] if "pts_time" in f]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-vf", "scale=64:36,format=gray",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    size = 64 * 36
    n = min(len(pts), len(raw) // size)
    diff = [0.0] * n
    for i in range(1, n):
        a, b = raw[(i - 1) * size: i * size], raw[i * size: (i + 1) * size]
        diff[i] = sum(abs(x - y) for x, y in zip(a, b)) / size
    # A camera can be most of a second late (virtual cameras, wireless links), and is almost never early.
    near = [i for i in range(1, n) if -.2 < pts[i] - t_audio < .8]
    rep = {"ok": False, "clap": True, "duration": round(dur, 2), "good": [], "notes": []}
    if not near or max(levels) < -30 or max(diff[i] for i in near) < 1:
        rep["notes"].append("没看清拍手：让手出现在画面中间，用力拍一下，再录一次")
        return rep
    peak = max(near, key=diff.__getitem__)
    # The hands stop at the last frame of the burst of motion.
    stop = next((i for i in range(peak, min(n - 1, peak + 6)) if diff[i + 1] < diff[peak] * .45), peak)
    offset = pts[stop] - t_audio
    frame = sorted(pts[i + 1] - pts[i] for i in range(n - 1))[(n - 1) // 2] if n > 1 else 0
    rep.update(offset=round(offset, 3), frame=round(frame, 3), fps=round(1 / frame, 1) if frame else None)
    if abs(offset) <= .045:
        rep["ok"] = True
        rep["good"].append(f"声画差约 {offset * 1000:+.0f} 毫秒（估算，精度约一帧），在可接受范围内")
    else:
        rep["notes"].append(f"声画差约 {offset * 1000:+.0f} 毫秒（估算）：再拍一次确认，稳定的话导出时会校正")
    return rep


if __name__ == "__main__":
    import sys
    print(json.dumps(analyze(Path(sys.argv[1]), None), ensure_ascii=False, indent=1))
