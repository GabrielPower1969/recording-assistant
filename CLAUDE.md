# CLAUDE.md: Recording Assistant

A local page for reading a script to camera. `README.md` is the user manual. `SKILL.md` is the skill, with the design reasons in Chinese.

## Commands

- Docker: `docker compose up -d`, then Chrome at http://localhost:8765/
- Native: `python3 scripts/serve.py <session-dir> --no-whisper`
- Export: `python3 scripts/export.py <session-dir> <out-dir>`
- Backup: `scripts/backup.sh <target-dir>`

## Map

| Path | What it is |
|---|---|
| `assets/coach.html` | The whole interface, one file. Served fresh on each request, so a refresh picks up edits |
| `scripts/serve.py` | Local HTTP server: saves takes, keeps picks and position, queues analysis |
| `scripts/analyze.py` | Per-take checks: level, clipping, pace, transcript against script |
| `scripts/export.py` | Cuts, levels and writes the picked takes |
| `sessions/<s>/light.json` | Lighting baseline: the first picked take's face measurement, or set by hand |
| `examples/demo/` | Demo script, copied into a new session |
| `sessions/` | User data, git-ignored: `lines.json`, `takes/`, `reports/`, `picks.json`, `calibration.json` |

## Invariants

1. People focus on expression. Warn only about problems that cannot be fixed later: clipping, very low level, skipped words.
2. The prompter runs on a clock. Never drive it from voice or recognition.
3. Sound and picture stay in one MediaRecorder, on one clock.
4. A take goes to disk when it stops. Deleting a take moves it to the Mac Trash, or to `takes/.trash/` where there is none (Docker). The app never erases a file, and take numbers are never reused.
5. Overlays (grid, outline, eye line) exist only in the page and never enter the recorded stream.
6. Nothing leaves the machine. The server refuses requests whose Host is not localhost, and compose publishes the port to 127.0.0.1 only.
7. Do not pass the script to the transcription model, or it will hear the script and miss skipped words.
8. The core stays on the Python standard library plus ffmpeg. Transcription stays optional.

## How to verify

Run Chrome headless with `--headless=new --use-fake-device-for-media-stream --use-fake-ui-for-media-stream`, drive it over CDP, record a take and check the file and report. Fake devices cannot prove real A/V offset, a real glass rig or a real trackpad.

Update this file in the same commit as any change to the architecture.
