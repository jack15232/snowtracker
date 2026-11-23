#!/bin/bash
# snowtracker Mac agent (runs under launchd):
#  - listens on ntfy.sh for "refresh:<id>" from the phone app and starts a GitHub update at once
#  - replies ack/busy/err so the app knows the Mac is awake
#  - triggers a routine update every 15 minutes
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
REPO="jack15232/snowtracker"
TOPIC="snowtracker-hpue6b4ugsklyjv2"
NTFY="https://ntfy.sh/$TOPIC"
STATE="$HOME/Library/Application Support/snowtracker"
mkdir -p "$STATE"
log() { echo "$(date '+%F %T') $*"; }

trigger() {  # $1 = force (true/false). Returns 0 started, 1 rate-limited, 2 failed
  local now last
  now=$(date +%s); last=$(cat "$STATE/last" 2>/dev/null || echo 0)
  if [ "$1" = true ] && [ $((now - last)) -lt 60 ]; then return 1; fi
  if gh workflow run update.yml -R "$REPO" -f force="$1" >/dev/null 2>"$STATE/gh.err"; then
    echo "$now" > "$STATE/last"; log "update started (force=$1)"; return 0
  fi
  log "gh failed: $(head -c 200 "$STATE/gh.err")"; return 2
}

# routine updates every 15 min
( while true; do trigger false; sleep 900; done ) &

# instant refresh requests from the app
while true; do
  # --speed-time drops a dead connection (e.g. after sleep) within 2 min; ntfy sends keepalives
  curl -sN --speed-limit 1 --speed-time 120 "$NTFY/raw?since=20s" | while IFS= read -r line; do
    case "$line" in
      refresh:*)
        id="${line#refresh:}"
        trigger true; rc=$?
        case $rc in 0) reply="ack:$id";; 1) reply="busy:$id";; *) reply="err:$id";; esac
        curl -s -d "$reply" "$NTFY" >/dev/null
        log "refresh request $id -> $reply";;
    esac
  done
  sleep 5
done
