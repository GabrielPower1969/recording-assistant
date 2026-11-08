#!/usr/bin/env python3
"""Fetch the face model for the lighting check: MediaPipe Face Landmarker (Google, Apache-2.0).

usage: fetch_vision.py [--quiet]

Downloads once into assets/vendor/, checks each file against a pinned SHA-256, and never runs anything
downloaded on this side: the files are served to the page, which runs them in the browser. The recording
works without them; only the lighting check is off.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "assets" / "vendor"
LIB = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/"
MODEL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
FILES = {
    "vision_bundle.mjs": (LIB + "vision_bundle.mjs", "40f4123dfcd75cfa58add046919cc6f52fde66f009ff582997c09ba54c6ba27c"),
    "wasm/vision_wasm_internal.js": (LIB + "wasm/vision_wasm_internal.js", "4a97e2520ba506c680ecd6ba6acfb146888afa0e2746d57f205352bc6ebb82eb"),
    "wasm/vision_wasm_internal.wasm": (LIB + "wasm/vision_wasm_internal.wasm", "f00ec4731faa23b3e714d00e88d4d10e2df5c0a427d3a2b4ae6e3526fdd14ef7"),
    "wasm/vision_wasm_nosimd_internal.js": (LIB + "wasm/vision_wasm_nosimd_internal.js", "927def7b465c51b86e4b3060f93646aca4e27121f4b8fc0483786e407ea9cf1f"),
    "wasm/vision_wasm_nosimd_internal.wasm": (LIB + "wasm/vision_wasm_nosimd_internal.wasm", "3821ea9b1f7fb8c549ef2a064ef5c85750bf375c545a49fd6eea0df44a95f1f4"),
    "face_landmarker.task": (MODEL, "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ready():
    return all((VENDOR / name).is_file() for name in FILES)


def fetch(quiet=False):
    """True when every file is present and matches its pinned hash."""
    ok = True
    for name, (url, want) in FILES.items():
        dest = VENDOR / name
        if dest.is_file() and sha(dest) == want:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        try:
            if not quiet:
                print(f"lighting check: downloading {name}", flush=True)
            with urllib.request.urlopen(url, timeout=60) as r, part.open("wb") as fh:
                while chunk := r.read(1 << 20):
                    fh.write(chunk)
            if sha(part) != want:
                raise ValueError("checksum does not match")
            part.replace(dest)
        except Exception as e:  # offline or changed upstream: the lighting check stays off
            part.unlink(missing_ok=True)
            print(f"lighting check: {name} not fetched ({e})", file=sys.stderr, flush=True)
            ok = False
    return ok


if __name__ == "__main__":
    sys.exit(0 if fetch("--quiet" in sys.argv) else 1)
