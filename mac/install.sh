#!/bin/bash
# One-line install:  curl -fsSL https://raw.githubusercontent.com/jack15232/snowtracker/main/mac/install.sh | bash
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v gh >/dev/null; then echo "GitHub CLI missing. Run:  brew install gh && gh auth login   then run this again."; exit 1; fi
if ! gh auth status >/dev/null 2>&1; then echo "GitHub CLI not logged in. Run:  gh auth login   then run this again."; exit 1; fi
DIR="$HOME/Library/Application Support/snowtracker"
mkdir -p "$DIR" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
curl -fsSL "https://raw.githubusercontent.com/jack15232/snowtracker/main/mac/agent.sh?t=$(date +%s)" -o "$DIR/agent.sh"
chmod +x "$DIR/agent.sh"
PLIST="$HOME/Library/LaunchAgents/com.jack.snowtracker.plist"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.jack.snowtracker</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/agent.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/snowtracker.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/snowtracker.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/com.jack.snowtracker" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 3
echo "snowtracker agent installed. Log: ~/Library/Logs/snowtracker.log"
tail -n 3 "$HOME/Library/Logs/snowtracker.log" 2>/dev/null || true
