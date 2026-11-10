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
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402
import fetch_vision  # noqa: E402

SAFE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SAFE_FILE = re.compile(r"^[A-Za-z0-9_-]{1,64}\.(mkv|webm|mp4)$")
EXT = {"video/x-matroska": "mkv", "video/webm": "webm", "video/mp4": "mp4"}
# The Mac Trash, so a deleted take can be put back. Inside a container there is none, and takes go to takes/.trash.
SYSTEM_TRASH = Path.home() / ".Trash"
ON_MAC = sys.platform == "darwin" and not os.environ.get("RA_CONTAINER")


LIGHT_KEYS = ("face", "side", "clip", "bg", "hue")
LIGHT_EXTRA = ("sat", "eye", "size", "x")


def clean_light(text):
    """Face lighting measured by the page: numbers only, so nothing else reaches disk."""
    try:
        raw = json.loads(text)
        out = {k: round(float(raw[k]), 3) for k in LIGHT_KEYS}
        out.update({k: round(float(raw[k]), 3) for k in LIGHT_EXTRA if k in raw})
        return out
    except (ValueError, TypeError, KeyError):
        return None


def gb(paths):
    return round(sum(p.stat().st_size for p in paths if p.is_file()) / 1e9, 2)


def to_system_trash(path: Path):
    """Move a file to the Mac Trash under a free name. Returns False when there is no usable Trash."""
    if not ON_MAC or not SYSTEM_TRASH.is_dir() or not os.access(SYSTEM_TRASH, os.W_OK):
        return False
    dest, n = SYSTEM_TRASH / path.name, 1
    while dest.exists():
        n += 1
        dest = SYSTEM_TRASH / f"{path.stem} {n}{path.suffix}"
    try:
        shutil.move(path, dest)
    except OSError:
        return False
    return True


def split_long(lines):
    """A segment written as one piece also comes in short pieces, cut at its long pauses (//), so the reader can
    choose the length. The short pieces cover the long one, the same way a project's own two lengths do."""
    out = []
    for l in lines:
        chunks = [c.strip() for c in re.split(r"\s*//\s*", l.get("t", "")) if c.strip()]
        if not l.get("anySize") or l.get("parts") or l.get("covers") or l.get("clap") or len(chunks) < 2:
            out.append(l)
            continue
        groups = []
        for c in chunks:  # a greeting of a few words is not worth its own take
            if groups and len(re.sub(r"[\s/，。！？,.!?]", "", groups[-1])) < 14:
                groups[-1] += " // " + c
            else:
                groups.append(c)
        if len(groups) > 1 and len(re.sub(r"[\s/，。！？,.!?]", "", groups[-1])) < 14:
            groups[-2:] = [groups[-2] + " // " + groups[-1]]
        if len(groups) < 2:
            out.append(l)
            continue
        kids = [{**{k: v for k, v in l.items() if k not in ("anySize", "orig", "edited", "target", "ref")},
                 "id": f"{l['id']}_p{i + 1}", "t": g, "size": "mid", "of": l["id"],
                 "chapter": f"{l.get('chapter', '')} {i + 1}/{len(groups)}".strip(),
                 "order": l.get("order", 0) + (i + 1) * 1e-4} for i, g in enumerate(groups)]
        out.append({**{k: v for k, v in l.items() if k != "anySize"}, "size": "long", "covers": [k["id"] for k in kids]})
        out += kids
    return out


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

    def edits(self):
        p = self.root / "edits.json"
        return json.loads(p.read_text("utf-8")) if p.exists() else {}

    def set_edit(self, key, text):
        """The reader's own wording for a segment (or one sentence of it). Kept beside lines.json, which a
        project may rebuild at any time; None puts the written script back."""
        with self.lock:
            edits = self.edits()
            if text is None:
                edits.pop(key, None)
            else:
                edits[key] = text
            tmp = self.root / "edits.json.part"
            tmp.write_text(json.dumps(edits, ensure_ascii=False, indent=1), "utf-8")
            tmp.replace(self.root / "edits.json")

    def lines(self):
        lines = json.loads((self.root / "lines.json").read_text("utf-8"))
        edits = self.edits()
        for l in lines:
            if l.get("parts"):  # sentences are shared by the long and the short segment that hold them
                hit = False
                for part in l["parts"]:
                    if part.get("id") in edits:
                        part["orig"], part["t"], hit = part["t"], edits[part["id"]], True
                if hit:
                    l["t"], l["edited"] = " // ".join(part["t"] for part in l["parts"]), True
            elif l["id"] in edits:
                l["orig"], l["t"], l["edited"] = l["t"], edits[l["id"]], True
        return split_long(lines)

    def picks(self):
        p = self.root / "picks.json"
        return json.loads(p.read_text("utf-8")) if p.exists() else {}

    def set_pick(self, line_id, name):
        with self.lock:
            picks = self.picks()
            if name:
                picks[line_id] = name
                # The first picked take sets the lighting every later take is compared with.
                dev = self.reports / (Path(name).stem + ".devices.json")
                if not (self.root / "light.json").exists() and dev.exists() and json.loads(dev.read_text("utf-8")).get("light"):
                    self.set_light_base(json.loads(dev.read_text("utf-8"))["light"])
            else:
                picks.pop(line_id, None)
            tmp = self.root / "picks.json.tmp"
            tmp.write_text(json.dumps(picks, ensure_ascii=False, indent=1), "utf-8")
            tmp.replace(self.root / "picks.json")

    def state(self):
        takes, pairs = {}, self.pairs()
        for f in sorted(self.takes.iterdir()):
            if not f.is_file() or not SAFE_FILE.match(f.name):
                continue
            line_id = f.stem.rsplit("_", 1)[0]
            rep = self.reports / (f.stem + ".json")
            dev = self.reports / (f.stem + ".devices.json")
            d = json.loads(dev.read_text("utf-8")) if dev.exists() else {}
            takes.setdefault(line_id, []).append({
                "av": pairs.get(f"{d.get('mic', '')}|{d.get('cam', '')}", {}).get("offset"),  # seconds the picture runs late
                "light": d.get("light"),
                "name": f.name,
                "size": f.stat().st_size,
                "report": json.loads(rep.read_text("utf-8")) if rep.exists() else None,
            })
        pos = self.root / "position.json"
        return {"lines": self.lines(), "takes": takes, "picks": self.picks(), "whisper": bool(self.whisper),
                "free_gb": round(shutil.disk_usage(self.root).free / 1e9, 1),
                "root": str(self.root), "takes_gb": gb(self.takes.iterdir()), "mac": ON_MAC,
                "old_trash": {"count": sum(1 for f in self.trash.iterdir() if SAFE_FILE.match(f.name)),
                              "gb": gb(self.trash.iterdir())},
                "position": json.loads(pos.read_text("utf-8")) if pos.exists() else None,
                "light_base": self.light_base(), "pairs": pairs}

    def light_base(self):
        p = self.root / "light.json"
        return json.loads(p.read_text("utf-8")) if p.exists() else None

    def set_light_base(self, light):
        tmp = self.root / "light.json.tmp"
        tmp.write_text(json.dumps(light), "utf-8")
        tmp.replace(self.root / "light.json")

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
            # Device notes outlive their takes, so a deleted take's number is never reused.
            nums = [int(m.group(1)) for f in list(self.takes.iterdir()) + list(self.trash.iterdir()) + list(self.reports.iterdir())
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
            if line_id == "_clap":  # a sync check, not a take: keep the number, not the file
                self.note_clap(f, rep)

    def pairs(self):
        path = self.root / "calibration.json"
        return (json.loads(path.read_text("utf-8")) if path.exists() else {}).get("pairs", {})

    def note_clap(self, f, rep):
        """One clap measures how late the picture is for this microphone and camera. The stored offset is the
        median of the last five, so one bad clap does not move it."""
        dev = self.reports / (f.stem + ".devices.json")
        d = json.loads(dev.read_text("utf-8")) if dev.exists() else {}
        key = f"{d.get('mic', '')}|{d.get('cam', '')}"
        path = self.root / "calibration.json"
        with self.lock:
            cal = json.loads(path.read_text("utf-8")) if path.exists() else {"pairs": {}}
            pair = cal["pairs"].setdefault(key, {})
            runs = pair.setdefault("runs", [])
            runs.append({"name": f.name, "offset": rep.get("offset"), "note": (rep.get("notes") or [""])[0] if rep.get("offset") is None else ""})
            del runs[:-8]
            seen = sorted(r["offset"] for r in runs if r["offset"] is not None)[-5:]
            if seen:
                seen = sorted(r["offset"] for r in [r for r in runs if r["offset"] is not None][-5:])
                pair["offset"] = round(seen[len(seen) // 2], 3)
                pair["source"] = f"median of {len(seen)} claps, {time.strftime('%Y-%m-%d')}: " + " ".join(f"{o * 1000:+.0f}" for o in seen) + " ms (about one frame of precision)"
            tmp = path.with_suffix(".json.part")
            tmp.write_text(json.dumps(cal, ensure_ascii=False, indent=1), "utf-8")
            tmp.replace(path)
        if not to_system_trash(f):
            shutil.move(f, self.trash / f.name)


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
        if m := re.match(r"^/vendor/((?:wasm/)?[A-Za-z0-9_.-]+)$", u.path):
            if m.group(1) in fetch_vision.FILES:
                kind = {".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm"}
                return self._file(fetch_vision.VENDOR / m.group(1), kind.get(Path(m.group(1)).suffix, "application/octet-stream"))
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
            {"mic": q.get("mic", [""])[0], "cam": q.get("cam", [""])[0], "light": clean_light(q.get("light", [""])[0])},
            ensure_ascii=False), "utf-8")
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
        if u.path == "/api/av":
            # The reader's own fine adjustment of how late the picture is for one microphone and camera, in seconds.
            key, off = f"{body.get('mic', '')}|{body.get('cam', '')}", body.get("offset")
            if isinstance(off, (int, float)) and -1 <= off <= 1 and len(key) < 300:
                path = s.root / "calibration.json"
                with s.lock:
                    cal = json.loads(path.read_text("utf-8")) if path.exists() else {"pairs": {}}
                    pair = cal["pairs"].setdefault(key, {})
                    pair["offset"], pair["source"] = round(off, 3), f"set by hand {time.strftime('%Y-%m-%d')}"
                    path.write_text(json.dumps(cal, ensure_ascii=False, indent=1), "utf-8")
                return self._json({"ok": True})
            return self._json({"error": "bad request"}, 400)
        if u.path == "/api/line":
            # {id: segment or sentence id, t: new wording, or null to put the script back}
            key, text = body.get("id", ""), body.get("t")
            known = {l["id"] for l in s.lines() if not l.get("of") and not l.get("parts")}
            known |= {p["id"] for l in s.lines() for p in l.get("parts", []) if p.get("id")}
            if key in known and (text is None or (isinstance(text, str) and 0 < len(text.strip()) < 6000)):
                s.set_edit(key, None if text is None else re.sub(r"[ \t]+", " ", text.strip()))
                return self._json({"ok": True})
            return self._json({"error": "bad request"}, 400)
        if u.path == "/api/position" and SAFE.match(body.get("id", "")):
            s.set_position(body["id"])
            return self._json({"ok": True})
        if u.path == "/api/light":
            light = clean_light(json.dumps(body.get("light")))
            if light:
                s.set_light_base(light)
                return self._json({"ok": True})
        if u.path == "/api/devices":
            return self._json({"calibrated": s.note_devices(str(body.get("mic", "")), str(body.get("cam", "")))})
        if u.path == "/api/trash":
            name = body.get("name", "")
            if SAFE_FILE.match(name) and (s.takes / name).is_file():
                # The Mac Trash first, so it can be put back from Finder; elsewhere a folder in the session.
                where = "trash" if to_system_trash(s.takes / name) else "folder"
                if where == "folder":
                    shutil.move(s.takes / name, s.trash / name)
                (s.reports / (Path(name).stem + ".json")).unlink(missing_ok=True)
                line_id = Path(name).stem.rsplit("_", 1)[0]
                if s.picks().get(line_id) == name:
                    s.set_pick(line_id, None)
                return self._json({"ok": True, "where": where})
        if u.path == "/api/empty-old-trash" and ON_MAC:
            moved = sum(to_system_trash(f) for f in list(s.trash.iterdir()) if SAFE_FILE.match(f.name))
            return self._json({"ok": True, "moved": moved})
        if u.path == "/api/reveal" and ON_MAC:
            name = body.get("name")
            if name is None:
                subprocess.run(["open", str(s.takes)], check=False)
                return self._json({"ok": True})
            if SAFE_FILE.match(name) and (s.takes / name).is_file():
                subprocess.run(["open", "-R", str(s.takes / name)], check=False)
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
    if not fetch_vision.ready():  # once, in the background: recording never waits for it
        threading.Thread(target=fetch_vision.fetch, daemon=True).start()
    Handler.session = Session(a.session.resolve(), None if a.no_whisper else a.whisper_python)
    print(f"Recording coach: open http://localhost:{a.port}/ in Chrome", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
