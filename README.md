# Recording Assistant

Read a script to camera, line by line, and let the software handle the rest. A local web page gives you a teleprompter, records sound and picture on one clock, saves every take to disk at once, and checks it. When you are done, it exports the takes you picked.

**The idea:** people focus on expression. Software handles levels, silence, timing and formats, and only warns you about problems that cannot be fixed later.

Everything runs on your machine. Nothing is uploaded.

> The interface is currently in Chinese. Scripts can be in English or Chinese.

## Quick start

### Docker (Linux or Mac)

```bash
docker compose up -d
```

Open <http://localhost:8765/> in Chrome and allow the camera and microphone. A demo script loads into `sessions/demo/`.

To record your own script, run with another session name and edit its `lines.json`:

```bash
SESSION=my-talk docker compose up -d
```

On Linux, if your user ID is not 1000, also set `RA_UID=$(id -u) RA_GID=$(id -g)` so that files belong to you.

The Docker image does not include the listening check, because the transcription library used here runs only on Apple Silicon. All other checks work.

### Mac, without Docker

You need Python 3.10 or later, `ffmpeg` and Chrome. The core uses only the Python standard library.

```bash
mkdir -p sessions/demo && cp examples/demo/lines.json sessions/demo/
python3 scripts/serve.py sessions/demo --no-whisper
```

For the listening check on Apple Silicon, install the optional dependency and point the server at that Python:

```bash
python3 -m venv .venv && .venv/bin/pip install mlx-whisper
python3 scripts/serve.py sessions/demo --whisper-python .venv/bin/python
```

The model downloads once from Hugging Face. After that, audio is transcribed locally.

## Recording

| Key | What it does |
|---|---|
| Space | Start or stop a take |
| C or Enter | Start over: drop the take in progress and count down again |
| Esc | Cancel this take without saving |
| + − | Text size: the teleprompter when one is showing, the script on the page otherwise |
| H | Hand gestures on or off |
| E | Change the wording of this segment. Saved in `edits.json` beside the script and used at once |
| Z | Long or short segments. A segment written as one piece is also offered cut at its long pauses (`//`) |
| ? | The full list of keys and gestures, on whichever screen has the focus |
| P | Pick the latest take and go to the next segment |
| ← → | Change segment when idle; move the reading position while recording |
| ↑ ↓ | Change scroll speed |
| T | Teleprompter for a glass rig, on a second screen when there is one |
| Shift+T | Teleprompter on this screen, whatever else is connected |
| M / K / L | In the teleprompter: flip the text / show yourself / scroll on or off |
| G | Framing guide: grid, head-and-shoulders outline, eye line. Never recorded |
| ⛶ on the preview | Full-screen preview, to set up framing before a take. Esc exits |
| V | Review what was recorded: one row a segment, open a row for its other takes, delete or clean up in one click |

### Hand gestures

Hold the gesture toward the camera for about a second. A bar on the preview fills while it counts.

| Gesture | What it does |
|---|---|
| 👍 thumb up | Start a take |
| 👎 thumb down | Start over |
| 🙅 forearms crossed | Cancel this take |

The hands are found by MediaPipe Gesture Recognizer, in the browser, on this machine. The hands have to leave
the pose before the next gesture counts.

### The text follows your voice

The scroll setting has three choices: **follow me**, steady, and still. "Follow me" never recognises words. It
listens for when you are speaking and how fast the syllables come, so the text speeds up and slows down with
you and waits while you pause. After each take read to the end it corrects itself against the syllable count
of the script. ↑ ↓ still trims the speed, and every change of speed or text size shows its new value on the
page and on the teleprompter glass.

### Deleting a take means "again"

The bin on a take in the side panel moves it to the Trash and starts the countdown for a new take at once.
In the review, the bin only deletes. "Clean up" there keeps one take a segment (the picked one, else the latest)
and moves the rest to the Trash. With nothing recorded, the review is empty.

### One take per segment

"Keep only the last take" is on by default: when a new take of a segment is saved, the earlier takes of that
segment go to the Trash, where they can be put back. Untick it in the side panel to keep every take. Disk space
comes back when the Trash is emptied.

### Chinese scripts read in lines

In a Chinese line a pause (`/` or `//`) is shown as a new line, with no pause marks. English lines keep ｜ and ｜｜.

### Small differences from the script are fine

A take that differs from the script by a few words is marked as information, not as a problem. Only a large
gap (most of a sentence missing) asks you to listen again.
| R / S | Play the reference clip / the standard pronunciation (English) |

The teleprompter runs on a clock at your own pace. It never follows your voice, because speech recognition is not reliable enough to hold the text back.

## Writing a script

Each session is a folder with a `lines.json`: a list of segments.

```json
{
  "id": "hello",
  "chapter": "Opening",
  "m": "Relaxed, like greeting a friend",
  "d": "Look into the lens. Smile before you speak.",
  "t": "Hi, / I'm *Sam*. // This is a {thorough|THUH-ruh} test.",
  "size": "long",
  "order": 1
}
```

Marks in `t`: `*word*` for stress, ` / ` for a pause, ` // ` for a longer pause, `{word|sounds like}` for a reading aid. In a Chinese line, an English word is followed by its meaning in full-width brackets, `volunteer（志愿者）`: the prompter shows it small and dim, it takes no prompter time and the missed-word check ignores it, while exports and subtitles keep it.

Optional fields: `zh` (translation), `p` (pronunciation note), `names` (names the transcript may mishear), `target` (original length in seconds), `ref` (a clip in `ref/`), `parts` (show the segment line by line), `lang: "zh"` (Chinese segment), `covers` and `anySize` (long and medium segment views). [SKILL.md](SKILL.md) describes them all.

## Lighting

The **打光** (lighting) panel reads your face the way a camera operator would. It finds the face with [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker) (Google, Apache-2.0, 478 face points, run in your browser), then measures:

| Check | How | Working target |
|---|---|---|
| Exposure | Median skin brightness on the forehead and cheeks | 45–70% |
| Key-to-fill ratio | One cheek against the other, in stops | up to 2:1 |
| Clipping | Pixels at 97% or more inside the face outline | under 1% |
| Background | Wall beside the head against the face | no more than half a stop brighter |
| Skin hue | Angle on a vectorscope against the skin-tone line (about 123°) | within 10° |
| Framing | Eye line, face size and position against the guide | eyes on the gold line |
| Consistency | Exposure and hue against the session baseline | within a quarter stop and 5° |

The first take you pick becomes the baseline, or press **以现在为准**. Each take stores its own measurement. The targets are common working values, not a standard. Only clipping and a very dark face cannot be fixed later.

The most common reason takes look different from day to day is automatic exposure and white balance in the camera. Set both to manual in the camera's own software.

The model (about 23 MB) downloads once on first start into `assets/vendor/`, checked against pinned SHA-256 hashes. Without it the lighting check is off and recording still works. To fetch it by hand: `python3 scripts/fetch_vision.py`.

## Turning the camera off

**关摄像头** on the preview or in the bottom bar saves the current take and turns the camera and microphone off. After 10 minutes with no input the page does this by itself, never during a take.

## Where takes are stored

Each take is saved in `<session>/takes/`. The recording page shows this folder, the size of the session and the free disk space. On a Mac, **打开文件夹** opens the folder and **定位** shows one take in Finder.

**删除** (delete) moves a take to the Mac Trash, so you can put it back from Finder. In Docker there is no Trash, so it goes to `takes/.trash/`. Deleting the picked take asks first. The app never erases a file.

## Export

```bash
python3 scripts/export.py sessions/demo out/demo
```

This writes one `.wav` and one `.mp4` per picked segment, cut to the spoken span and levelled to -20 LUFS, plus `manifest.json`. Takes are never changed.

## What the machine can and cannot check

| Can check | Cannot check |
|---|---|
| Clipping and very low level | Whether the tone is right |
| Skipped or changed words (with the listening check) | Whether the pronunciation is natural |

## Limits

- Video is high-bitrate H.264 from the browser, not lossless. The browser recorder has no lossless video option.
- A/V offset is stored per microphone and camera pair, and defaults to 0 for a new pair. It is not measured automatically.
- Tested in Chrome. Other browsers are untested.
- So far the native Mac run has been tested end to end with simulated devices. The Docker setup has not been run yet, so please report any problems.

## Backup and restore

```bash
scripts/backup.sh /path/to/target
```

To restore, unpack the tar in the project folder and run `docker compose up -d`.

## As a Claude Code skill

Clone this repository to `.claude/skills/recording-coach`. Claude reads [SKILL.md](SKILL.md). [CLAUDE.md](CLAUDE.md) is the map for working on the code.

## License

[MIT](LICENSE)

## 中文速览

**录音助手：** 对着镜头按稿子逐段读，其他交给软件。本地网页提供提词器，声音和画面用同一个时钟录制，每遍立刻存盘并自动检查，最后导出选中的遍数。所有数据都留在本机，不上传。

- **运行：** `docker compose up -d`，然后用 Chrome 打开 <http://localhost:8765/>。
- **写稿：** 在 `sessions/<名字>/lines.json` 写稿，格式见 `examples/demo/lines.json`。
- **玻璃提词器：** 按 T，按 M 换翻转。有第二块屏时会自动开到那块屏上。
- **构图：** 按 G 开关构图线，线不进录像。
- **听写检查：** 只支持 Apple Silicon 的 Mac 原生运行，Docker 版没有。
- **导出：** `python3 scripts/export.py sessions/<名字> out/<名字>`。
- **存放和删除：** 录制页右侧显示存放文件夹和占用空间。“删除”在 Mac 上是移到废纸篓，可以放回。
- **备份：** `scripts/backup.sh <目标目录>`。
