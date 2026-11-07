#!/usr/bin/env python3
"""Export the picked takes: cut to the spoken span, constant frame rate, sound and picture together.

usage: export.py <session-dir> <out-dir> [--fps 30]

Writes <id>.wav (48 kHz mono, lossless) and <id>.mp4 (camera, same span) plus manifest.json. Cuts snap to
quiet room just outside the speech, so no word is clipped. Each camera and microphone pair has its own stored A/V offset (calibration.json). Each line is levelled to one loudness. Takes stay untouched. Lines with no pick are listed, not guessed.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import plain  # noqa: E402

PAD_HEAD, PAD_TAIL = .12, .18
TARGET_LUFS, MAX_GAIN, PEAK_LIMIT = -20.0, 18.0, -1.0


def gain_for(rep):
    """Bring every line to one loudness, so the reader need not hold a position; never push a peak over the limit."""
    if rep.get("lufs") is None:
        return 0.0
    gain = max(-MAX_GAIN, min(MAX_GAIN, TARGET_LUFS - rep["lufs"]))
    return round(min(gain, PEAK_LIMIT - rep.get("peak", 0.0)), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    lines = json.loads((a.session / "lines.json").read_text("utf-8"))
    picks = json.loads((a.session / "picks.json").read_text("utf-8"))
    cal_file = a.session / "calibration.json"
    pairs = json.loads(cal_file.read_text("utf-8")).get("pairs", {}) if cal_file.exists() else {}
    manifest, missing, uncalibrated = [], [], set()
    # A picked long segment replaces the medium segments it covers.
    replaced = {c for l in lines if picks.get(l["id"]) for c in l.get("covers", [])}
    for line in lines:
        if line["id"] in replaced or (line.get("covers") and not picks.get(line["id"])):
            continue
        if line.get("clap"):
            continue
        name = picks.get(line["id"])
        if not name:
            missing.append(line["id"])
            continue
        rep = json.loads((a.session / "reports" / (Path(name).stem + ".json")).read_text("utf-8"))
        start = max(0, rep["head"] - PAD_HEAD)
        end = min(rep["duration"], rep["duration"] - rep["tail"] + PAD_TAIL)
        src = a.session / "takes" / name
        dev_file = a.session / "reports" / (Path(name).stem + ".devices.json")
        dev = json.loads(dev_file.read_text("utf-8")) if dev_file.exists() else {}
        key = f"{dev.get('mic', '')}|{dev.get('cam', '')}"
        offset = pairs.get(key, {}).get("offset", 0.0)
        if key not in pairs:
            uncalibrated.add(key)
        wav, mp4 = a.out / f"{line['id']}.wav", a.out / f"{line['id']}.mp4"
        common = ["ffmpeg", "-v", "error", "-y"]
        subprocess.run(common + ["-i", str(src), "-map", "0:a:0", "-af",
                                 f"atrim={start:.4f}:{end:.4f},asetpts=PTS-STARTPTS,volume={gain_for(rep)}dB", "-ac", "1", "-ar", "48000",
                                 "-c:a", "pcm_s16le", str(wav)], check=True)
        # A positive offset means the picture runs late, so it is read that much later than the sound.
        v0, v1 = start + offset, end + offset
        subprocess.run(common + ["-i", str(src), "-map", "0:v:0", "-vf",
                                 f"trim={max(0, v0):.4f}:{v1:.4f},setpts=PTS-STARTPTS,fps={a.fps}",
                                 "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
                                 "-an", str(mp4)], check=True)
        manifest.append({"id": line["id"], "take": name, "start": round(start, 3), "end": round(end, 3),
                         "seconds": round(end - start, 3), "gain_db": gain_for(rep), "av_offset": offset, "t": plain(line["t"]), "parts": [p["id"] for p in line.get("parts", [])],
                         "order": line.get("order", 0)})
    manifest.sort(key=lambda m: m["order"])
    (a.out / "manifest.json").write_text(json.dumps({"lines": manifest, "missing": missing, "uncalibrated": sorted(uncalibrated)},
                                                    ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(manifest)} exported, {len(missing)} without a pick, {len(uncalibrated)} uncalibrated device pairs")
    if missing:
        print("missing:", " ".join(missing))


if __name__ == "__main__":
    main()
