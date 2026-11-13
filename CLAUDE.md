# CLAUDE.md: Recording Assistant

A local page for reading a script to camera. `README.md` is the user manual. `SKILL.md` is the skill, with the design reasons in Chinese.

## Commands

- Docker: `docker compose up -d`, then Chrome at http://localhost:8765/
- Native: `python3 scripts/serve.py <version-dir> [<version-dir> ...] --no-whisper` (adds the project to the list, then serves; if a coach already runs on the port it only adds)
- Mac, always on: `scripts/install_service.sh` (launchd agent `local.recording-coach`, starts at login); `--uninstall` removes it
- Export: `python3 scripts/export.py <session-dir> <out-dir>`
- Backup: `scripts/backup.sh <target-dir>`

## Map

| Path | What it is |
|---|---|
| `design/` | Design assets for other projects: `DESIGN.md` (rules), `tokens.css` (generated), `screenshots/`, and `README.md` listing every file with a raw GitHub link |
| `scripts/export_tokens.py` | Copies the token block of `assets/coach.html` (between `tokens:start` and `tokens:end`) to `design/tokens.css`; `--check` fails when stale |
| `assets/brand/` | The icon, copied from FlowGT Recorder and only scaled (see its README): tab icon, page mark, iPad home icon |
| `assets/coach.html` | The whole interface, one file. Served fresh on each request, so a refresh picks up edits |
| `scripts/serve.py` | Local HTTP server: saves takes, keeps picks and position, queues analysis. `Hub` holds every project, `Versions` the folders of one project; requests carry `?p=<project>&v=<version>` |
| `scripts/install_service.sh` | Keeps the server running at login on a Mac |
| `~/.recording-coach.json` | The project list: each project's version folders and the version last used, newest first. `RA_MEMORY` moves it (compose puts it in `/data`) |
| `scripts/analyze.py` | Per-take checks: level, clipping, pace, transcript against script |
| `scripts/export.py` | Cuts, levels and writes the picked takes |
| `sessions/<s>/light.json` | Lighting baseline: the first picked take's face measurement, or set by hand |
| `scripts/fetch_vision.py` | Downloads the face model into `assets/vendor/` (git-ignored), pinned by SHA-256 |
| `examples/demo/` | Demo script, copied into a new session |
| `sessions/` | User data, git-ignored: `lines.json`, `takes/`, `reports/`, `picks.json`, `calibration.json` |
| `<version>/session.json` · `glossary.json` | Optional: the version's display name; English terms and their Chinese meanings for the auto gloss |

## Invariants

1. People focus on expression. Warn only about problems that cannot be fixed later: clipping, very low level, skipped words.
2. The prompter runs on a clock. Never drive it from voice or recognition.
3. Sound and picture stay in one MediaRecorder, on one clock.
4. A take goes to disk when it stops. Deleting a take moves it to the Mac Trash, or to `takes/.trash/` where there is none (Docker). The app never erases a file, and take numbers are never reused.
5. Overlays (grid, outline, eye line) exist only in the page and never enter the recorded stream.
6. Nothing leaves the machine. The server refuses requests whose Host is not localhost, and compose publishes the port to 127.0.0.1 only.
7. Do not pass the script to the transcription model, or it will hear the script and miss skipped words.
8. The core stays on the Python standard library plus ffmpeg. Transcription and the face model stay optional: without them, recording still works.
9. The camera turns off after 10 idle minutes, never during a take or an upload.
10. One folder per version (one language, one cut). Takes, picks and position never mix between versions; switching (key B) only changes which folder the page talks to.
11. Every setting the user changes is remembered: project list and last version in `~/.recording-coach.json`, position per folder, theme and current project in the browser.
12. Colours come only from the tokens on `:root` (light) and their dark set. The look is FlowGT Recorder's "Faceplate" (aluminium plate, cream paper, dark glass) with a Bauhaus layer on top: round convex keys, rounded corners, red = record, yellow = move on, blue = chosen. Never mark a group with a coloured stripe on one side; use labels, hairlines and material. Restyling never moves the layout.

## How to verify

Run Chrome headless with `--headless=new --use-fake-device-for-media-stream --use-fake-ui-for-media-stream`, drive it over CDP, record a take and check the file and report. Fake devices cannot prove real A/V offset, a real glass rig or a real trackpad.

After changing a colour, radius or font run `python3 scripts/export_tokens.py`; after changing the look also update `design/DESIGN.md` and retake `design/screenshots/` in the same commit.

Update this file in the same commit as any change to the architecture.
