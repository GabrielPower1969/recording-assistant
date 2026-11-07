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
| Esc | Cancel this take without saving |
| P | Pick the latest take and go to the next segment |
| ← → | Change segment when idle; move the reading position while recording |
| ↑ ↓ | Change scroll speed |
| T | Teleprompter for a glass rig, on a second screen when there is one |
| M / C / L | In the teleprompter: flip the text / show yourself / scroll on or off |
| G | Framing guide: grid, head-and-shoulders outline, eye line. Never recorded |
| V | Review all segments and play the picked takes |
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

Marks in `t`: `*word*` for stress, ` / ` for a pause, ` // ` for a longer pause, `{word|sounds like}` for a reading aid.

Optional fields: `zh` (translation), `p` (pronunciation note), `names` (names the transcript may mishear), `target` (original length in seconds), `ref` (a clip in `ref/`), `parts` (show the segment line by line), `lang: "zh"` (Chinese segment), `covers` and `anySize` (long and medium segment views). [SKILL.md](SKILL.md) describes them all.

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
- **备份：** `scripts/backup.sh <目标目录>`。
