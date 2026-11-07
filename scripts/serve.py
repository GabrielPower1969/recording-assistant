#!/usr/bin/env python3
"""Recording coach: local-only server. Saves every take to disk as soon as it stops, then analyses it.

usage: serve.py <session-dir> [--host 127.0.0.1] [--port 8765] [--whisper-python PATH] [--no-whisper]

<session-dir> holds lines.json and optional ref/<id>.mp3 (reference clips); takes go to
<session-dir>/takes/, reports to <session-dir>/reports/, picks to <session-dir>/picks.json.
Binds 127.0.0.1 only. Nothing leaves the machine. Standard library plus ffmpeg/ffprobe.
"""
import argparse
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402

SAFE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SAFE_FILE = re.compile(r"^[A-Za-z0-9_-]{1,64}\.(mkv|webm|mp4)$")
EXT = {"video/x-matroska": "mkv", "video/webm": "webm", "video/mp4": "mp4"}


class Session:
    def __init__(self, root: Path, whisper_py: str | None):
        self.root = root
        self.takes = root / "takes"
        self.reports = root / "reports"
        self.trash = root / "takes" / ".trash"
        for d in (self.takes, self.reports, self.trash):
            d.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.jobs: queue.Queue = queue.Queue()
        self.whisper = analyze.Whisper(whisper_py) if whisper_py else None
        threading.Thread(target=self._worker, daemon=True).start()
        # Takes saved before a crash still get their report.
        for f in sorted(self.takes.iterdir()):
            if f.is_file() and SAFE_FILE.match(f.name) and not (self.reports / (f.stem + ".json")).exists():
                self.jobs.put(f)

    def lines(self):
        return json.loads((self.root / "lines.json").read_text("utf-8"))

    def picks(self):
        p = self.root / "picks.json"
        return json.loads(p.read_text("utf-8")) if p.exists() else {}

    def set_pick(self, line_id, name):
        with self.lock:
            picks = self.picks()
            if name:
                picks[line_id] = name
            else:
                picks.pop(line_id, None)
            tmp = self.root / "picks.json.tmp"
            tmp.write_text(json.dumps(picks, ensure_ascii=False, indent=1), "utf-8")
            tmp.replace(self.root / "picks.json")

    def state(self):
        takes = {}
        for f in sorted(self.takes.iterdir()):
            if not f.is_file() or not SAFE_FILE.match(f.name):
                continue
            line_id = f.stem.rsplit("_", 1)[0]
            rep = self.reports / (f.stem + ".json")
            takes.setdefault(line_id, []).append({
                "name": f.name,
                "size": f.stat().st_size,
                "report": json.loads(rep.read_text("utf-8")) if rep.exists() else None,
            })
        pos = self.root / "position.json"
        return {"lines": self.lines(), "takes": takes, "picks": self.picks(), "whisper": bool(self.whisper),
                "free_gb": round(shutil.disk_usage(self.root).free / 1e9, 1),
                "position": json.loads(pos.read_text("utf-8")) if pos.exists() else None}

    def note_devices(self, mic, cam):
        """A stored offset waiting for its devices goes to the first pair seen; later pairs start uncalibrated."""
        path = self.root / "calibration.json"
        with self.lock:
            cal = json.loads(path.read_text("utf-8")) if path.exists() else {"pairs": {}}
            key = f"{mic}|{cam}"
            if key not in cal["pairs"] and cal.get("unclaimed"):
                cal["pairs"][key] = cal.pop("unclaimed")
                path.write_text(json.dumps(cal, ensure_ascii=False, indent=1), "utf-8")
            return key in cal["pairs"]

    def set_position(self, line_id):
        tmp = self.root / "position.json.tmp"
        tmp.write_text(json.dumps(line_id), "utf-8")
        tmp.replace(self.root / "position.json")

    def next_name(self, line_id, ext):
        with self.lock:
            nums = [int(m.group(1)) for f in list(self.takes.iterdir()) + list(self.trash.iterdir())
                    if (m := re.match(re.escape(line_id) + r"_(\d+)\.", f.name))]
            n = max(nums, default=0) + 1
            name = f"{line_id}_{n}.{ext}"
            (self.takes / (name + ".part")).touch()
            return name

    def _worker(self):
        while True:
            f = self.jobs.get()
            line_id = f.stem.rsplit("_", 1)[0]
            line = next((l for l in self.lines() if l["id"] == line_id), None)
            try:
                rep = analyze.analyze(f, line, self.whisper)
            except Exception as e:  # a bad report must never lose or block a take
                rep = {"ok": False, "notes": [f"分析失败：{e}"], "error": str(e)}
            tmp = self.reports / (f.stem + ".json.tmp")
            tmp.write_text(json.dumps(rep, ensure_ascii=False, indent=1), "utf-8")
            tmp.replace(self.reports / (f.stem + ".json"))


class Handler(BaseHTTPRequestHandler):
    session: Session = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype=None):
        if not path.is_file():
            return self._json({"error": "not found"}, 404)
        size = path.stat().st_size
        start, end, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else end
            else:
                start = max(0, size - int(m.group(2)))
            end, code = min(end, size - 1), 206
        self.send_response(code)
        self.send_header("Content-Type", ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with path.open("rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0 and (chunk := fh.read(min(1 << 20, left))):
                self.wfile.write(chunk)
                left -= len(chunk)

    def _local_only(self):
        """Refuse requests whose Host is not this machine (blocks DNS rebinding)."""
        host = self.headers.get("Host", "").rsplit(":", 1)[0]
        if host in ("localhost", "127.0.0.1"):
            return True
        self._json({"error": "local only"}, 403)
        return False

    def do_GET(self):
        if not self._local_only():
            return
        s, u = self.session, urlparse(self.path)
        if u.path in ("/", "/coach.html"):
            return self._file(HERE.parent / "assets" / "coach.html", "text/html; charset=utf-8")
        if u.path == "/api/state":
            return self._json(s.state())
        if m := re.match(r"^/take/([^/]+)$", u.path):
            if SAFE_FILE.match(m.group(1)):
                return self._file(s.takes / m.group(1), "video/x-matroska" if m.group(1).endswith("mkv") else None)
        if m := re.match(r"^/ref/([A-Za-z0-9_-]+\.mp3)$", u.path):
            return self._file(s.root / "ref" / m.group(1), "audio/mpeg")
        self._json({"error": "not found"}, 404)

    def do_PUT(self):
        if not self._local_only():
            return
        s, u = self.session, urlparse(self.path)
        q = parse_qs(u.query)
        line_id = q.get("id", [""])[0]
        ctype = self.headers.get("Content-Type", "").split(";")[0].strip()
        if u.path != "/api/take" or not SAFE.match(line_id) or ctype not in EXT:
            return self._json({"error": "bad request"}, 400)
        left = int(self.headers.get("Content-Length", 0))
        name = s.next_name(line_id, EXT[ctype])
        part = s.takes / (name + ".part")
        with part.open("wb") as fh:
            while left > 0 and (chunk := self.rfile.read(min(1 << 20, left))):
                fh.write(chunk)
                left -= len(chunk)
        if left:
            return self._json({"error": "upload cut short"}, 400)  # .part stays on disk
        final = s.takes / name
        part.replace(final)
        (s.reports / (final.stem + ".devices.json")).write_text(json.dumps(
            {"mic": q.get("mic", [""])[0], "cam": q.get("cam", [""])[0]}, ensure_ascii=False), "utf-8")
        s.jobs.put(final)
        self._json({"name": name})

    def do_POST(self):
        if not self._local_only():
            return
        s, u = self.session, urlparse(self.path)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if u.path == "/api/pick":
            line_id, name = body.get("id", ""), body.get("name")
            if SAFE.match(line_id) and (name is None or SAFE_FILE.match(name)):
                s.set_pick(line_id, name)
                return self._json({"ok": True})
        if u.path == "/api/position" and SAFE.match(body.get("id", "")):
            s.set_position(body["id"])
            return self._json({"ok": True})
        if u.path == "/api/devices":
            return self._json({"calibrated": s.note_devices(str(body.get("mic", "")), str(body.get("cam", "")))})
        if u.path == "/api/trash":
            name = body.get("name", "")
            if SAFE_FILE.match(name) and (s.takes / name).is_file():
                shutil.move(s.takes / name, s.trash / name)  # kept on disk, never deleted
                (s.reports / (Path(name).stem + ".json")).unlink(missing_ok=True)
                line_id = Path(name).stem.rsplit("_", 1)[0]
                if s.picks().get(line_id) == name:
                    s.set_pick(line_id, None)
                return self._json({"ok": True})
        self._json({"error": "bad request"}, 400)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session", type=Path)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 only inside a container whose port is published to localhost")
    ap.add_argument("--whisper-python", default=os.environ.get("COACH_WHISPER_PY"))
    ap.add_argument("--no-whisper", action="store_true")
    a = ap.parse_args()
    if not (a.session / "lines.json").exists():
        sys.exit(f"{a.session}/lines.json is missing")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} is required")
    Handler.session = Session(a.session.resolve(), None if a.no_whisper else a.whisper_python)
    print(f"Recording coach: open http://localhost:{a.port}/ in Chrome", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
