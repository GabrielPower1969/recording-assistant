#!/usr/bin/env python3
"""Write a double-click launcher `录音台-<name>.command` into a project folder.

    python3 launcher.py <project folder> <project key> [version key]

Double-clicking it starts the coach server if it is down and opens Chrome on that project/version.
"""
import sys, os
from pathlib import Path
from urllib.parse import quote

folder, key = Path(sys.argv[1]), sys.argv[2]
ver = sys.argv[3] if len(sys.argv) > 3 else ""
url = f"http://localhost:8765/?p={quote(key)}" + (f"&v={quote(ver)}" if ver else "")
out = folder / f"录音台-{key}.command"
out.write_text(f"""#!/bin/zsh
# Opens the recording coach on this project. Made by recording-coach/scripts/launcher.py
if ! curl -s -o /dev/null http://localhost:8765/api/state; then
  launchctl kickstart gui/$(id -u)/local.recording-coach 2>/dev/null || \\
  (cd "$HOME/Documents/workspace/.claude/skills/recording-coach" && nohup python3 scripts/serve.py --port 8765 >/dev/null 2>&1 &)
  for i in {{1..20}}; do curl -s -o /dev/null http://localhost:8765/api/state && break; sleep 0.5; done
fi
open -a "Google Chrome" "{url}"
osascript -e 'tell application "Terminal" to close (every window whose name contains "录音台")' >/dev/null 2>&1 &
exit 0
""", "utf-8")
os.chmod(out, 0o755)
print(out)
