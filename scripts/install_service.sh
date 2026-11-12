#!/bin/bash
# Keep the recording coach running on this Mac, so http://localhost:8765/ always opens the list of recording
# projects: started at login, restarted if it stops. Projects are added with
#   python3 scripts/serve.py <version-dir> [<version-dir> ...]
# (or "添加项目…" on the page) and stay on the list in ~/.recording-coach.json.
#
#   scripts/install_service.sh [--whisper-python PATH] [--port 8765]   install or update
#   scripts/install_service.sh --uninstall                             stop and remove
set -euo pipefail
LABEL="local.recording-coach"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/recording-coach.log"
HERE="$(cd "$(dirname "$0")" && pwd)"
PORT=8765
WHISPER="${COACH_WHISPER_PY:-}"

[ "$(uname)" = "Darwin" ] || { echo "Mac only. Elsewhere run scripts/serve.py yourself (or in Docker)." >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true; rm -f "$PLIST"; echo "removed $LABEL"; exit 0 ;;
    --whisper-python) WHISPER="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 1 ;;
  esac
done

PY="$(command -v python3)"
command -v ffmpeg >/dev/null || { echo "ffmpeg is required (brew install ffmpeg)" >&2; exit 1; }
ARGS="<string>$PY</string><string>$HERE/serve.py</string><string>--port</string><string>$PORT</string>"
[ -n "$WHISPER" ] && ARGS="$ARGS<string>--whisper-python</string><string>$WHISPER</string>"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>$ARGS</array>
  <key>WorkingDirectory</key><string>$HERE</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$(dirname "$(command -v ffmpeg)"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "recording coach runs at login: http://localhost:$PORT/   (log: $LOG)"
