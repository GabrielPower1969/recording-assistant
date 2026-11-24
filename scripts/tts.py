#!/usr/bin/env python3
"""Make a listen-first clip for every line with local Qwen3-TTS: <version>/tts/<id>.mp3 + tts/manifest.json.

    python3 tts.py <version folder> [--voice ryan] [--instruct "..."] [--force]

Runs fully on this Mac (mlx-audio); nothing is sent anywhere and no model is downloaded here: it uses the
Qwen3-TTS model already in the Hugging Face cache and the Python that has mlx-audio installed.
  QWEN_TTS_PYTHON  python with mlx_audio (default: <workspace>/4-business/doodlive/.venv-voice/bin/python)
  QWEN_TTS_MODEL   model id or local folder (default: mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit)
manifest.json keeps the text each clip was made from. When a line is changed on the page (E), its text no longer
matches, so the page plays ordinary browser speech for that line until this script is run again.
"""
import argparse, contextlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path

WS = Path(__file__).resolve().parents[4]          # <workspace>/.claude/skills/recording-coach/scripts
PY = os.environ.get("QWEN_TTS_PYTHON", str(WS / "4-business/doodlive/.venv-voice/bin/python"))
MODEL = os.environ.get("QWEN_TTS_MODEL", "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit")
LANGS = {"en": "english", "zh": "chinese"}
INSTRUCT = {"en": "A warm, confident New Zealand tech community host. Clear, natural, upbeat, not rushed.",
            "zh": "热情、自然、清楚的科技社区主持人，语速适中。"}

def plain(t: str) -> str:
    """Same rule as the page: drop *stress* marks and pause marks."""
    t = re.sub(r"\{([^|}]+)\|[^}]*\}", r"\1", t).replace("*", "")
    t = re.sub(r"\s*//\s*", ". ", t)
    t = re.sub(r"\s*/\s*", ", ", t)
    return re.sub(r"\s+", " ", t).strip()

def page_text(t: str) -> str:
    """Key for manifest.json; must equal plain() in coach.html (marks removed, spaces collapsed)."""
    t = re.sub(r"\{([^|}]+)\|[^}]*\}", r"\1", t).replace("*", "")
    return re.sub(r"\s+", " ", re.sub(r"\s*/+\s*", " ", t)).strip()

@contextlib.contextmanager
def gpu_lock():
    """Share the doodlive GPU lock when it is there, so two Qwen runs never fight over the GPU."""
    sys.path.insert(0, str(WS / "4-business/doodlive/tools/story"))
    try:
        import tts_lock
        with tts_lock.held("recording-coach tts"):
            yield
    except ImportError:
        yield

def main():
    try:
        import mlx_audio  # noqa: F401
    except ImportError:
        if Path(PY).exists() and not os.environ.get("_TTS_REEXEC"):
            os.environ["_TTS_REEXEC"] = "1"
            os.execv(PY, [PY, *sys.argv])
        sys.exit(f"mlx_audio not found. Set QWEN_TTS_PYTHON to a python that has it (tried {PY}).")
    import numpy as np, soundfile as sf
    from mlx_audio.tts.utils import load_model

    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--voice", default="ryan")
    ap.add_argument("--instruct")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    root = Path(a.version)
    data = json.loads((root / "lines.json").read_text("utf-8"))
    lines = data["lines"] if isinstance(data, dict) else data
    out_dir = root / "tts"; out_dir.mkdir(exist_ok=True)
    mf = out_dir / "manifest.json"
    manifest = json.loads(mf.read_text("utf-8")) if mf.exists() else {}
    todo = []
    for L in lines:
        if L.get("clap") or not re.match(r"^[A-Za-z0-9_-]+$", L["id"]):
            continue
        key = page_text(L["t"])
        mkey = key + ("|" + json.dumps(L["say"], sort_keys=True) if L.get("say") else "")
        if not a.force and manifest.get(L["id"]) in (key, mkey) and manifest.get(L['id'] + '#say') == L.get('say') and (out_dir / f"{L['id']}.mp3").exists():
            print("skip", L["id"]); continue
        todo.append((L, key))
    if not todo:
        return
    with gpu_lock():
        m = load_model(MODEL)
        for L, key in todo:
            lang = "zh" if L.get("lang") == "zh" else "en"
            spoken = plain(L["t"])
            for w, r in (L.get("say") or {}).items():  # how a word is read, e.g. {"CITANZ": "Cita"}
                spoken = spoken.replace(w, r)
            res = list(m.generate(text=spoken, voice=a.voice, instruct=a.instruct or INSTRUCT[lang],
                                  lang_code=LANGS[lang], verbose=False))
            with tempfile.TemporaryDirectory() as d:
                wav = Path(d) / "a.wav"
                sf.write(wav, np.concatenate([np.array(r.audio) for r in res]), m.sample_rate)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                                "-af", "loudnorm=I=-16:TP=-1.5", "-b:a", "128k", str(out_dir / f"{L['id']}.mp3")], check=True)
            manifest[L["id"]] = key
            if L.get("say"): manifest[L["id"] + "#say"] = L["say"]
            mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
            print("ok", L["id"])

if __name__ == "__main__":
    main()
