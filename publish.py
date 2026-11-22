"""Commit docs/data/summary.json and push, only if it changed."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=check)


def publish():
    git("add", "docs/data/summary.json")
    if (ROOT / "alerts" / "sent.json").exists():
        git("add", "alerts/sent.json")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("publish: no change")
        return
    git("commit", "-q", "-m", "data: update summary")
    git("pull", "-q", "--rebase", "--autostash", check=False)
    r = git("push", "-q", check=False)
    if r.returncode != 0:
        print("publish: push failed:\n" + r.stderr, file=sys.stderr)
        sys.exit(1)
    print("publish: pushed")


if __name__ == "__main__":
    publish()
