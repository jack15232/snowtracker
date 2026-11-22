"""Web Push snow alerts.

Rule: notify once per date when a coming day (tomorrow .. day 7) is forecast 10 cm+ at the alert
band with >= ALERT_PROB chance; notify again if the same date later reaches the "big day" level.

Secrets (GitHub repo -> Settings -> Secrets and variables -> Actions):
  VAPID_PRIVATE_KEY   signing key (base64url, raw P-256 scalar)
  PUSH_SUBSCRIPTION   JSON copied from the app (one object, or a list for several devices)

  python3 -m snowcast.alerts --test     send a test notification
"""

import json
import os
import sys
from pathlib import Path

from . import config

SENT_FILE = config.ROOT / "alerts" / "sent.json"


def _load_sent():
    try:
        return json.loads(SENT_FILE.read_text())
    except Exception:
        return {}


def _save_sent(sent):
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    # keep only recent dates
    keep = dict(sorted(sent.items())[-30:])
    SENT_FILE.write_text(json.dumps(keep, indent=1, sort_keys=True))


def _subscriptions():
    raw = os.environ.get("PUSH_SUBSCRIPTION", "").strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def send(title, body, url="./", tag=None):
    """Send to every subscribed device. Returns (sent_count, errors)."""
    key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    subs = _subscriptions()
    if not key or not subs:
        return 0, ["alerts not configured (VAPID_PRIVATE_KEY / PUSH_SUBSCRIPTION secret missing)"]
    from pywebpush import WebPushException, webpush
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or title})
    n, errors = 0, []
    for sub in subs:
        try:
            webpush(subscription_info=sub, data=payload, vapid_private_key=key,
                    vapid_claims={"sub": config.ALERT_CONTACT}, ttl=6 * 3600)
            n += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            errors.append(f"push failed ({code}): {str(e)[:150]}"
                          + (" - subscription expired, turn alerts on again in the app" if code in (404, 410) else ""))
    return n, errors


def _fmt_day(d):
    from datetime import date
    y, m, dd = map(int, d["date"].split("-"))
    return date(y, m, dd).strftime("%a %-d %b")


def check(summary):
    """Return list of (date, level, title, body) that should be sent now, updating nothing."""
    band = summary["bands"].get(config.ALERT_BAND)
    if not band:
        return []
    sent = _load_sent()
    out = []
    for d in band["days"][1:]:              # tomorrow onwards
        s = d.get("snow")
        if not s or s.get("p_gt10") is None:
            continue
        level = 0
        if s["p_gt10"] >= config.ALERT_PROB:
            level = 1
        if (s.get("p_gt30") or 0) >= config.ALERT_PROB:
            level = 2
        if level == 0 or sent.get(d["date"], 0) >= level:
            continue
        day = _fmt_day(d)
        trip = " (trip day!)" if config.TRIP_START <= d["date"] <= config.TRIP_END else ""
        title = (f"Big snow day: {day}" if level == 2 else f"10cm+ day: {day}") + trip
        body = (f"~{round(s['p50'])} cm at {band['label']} ({round(s['p_gt10'] * 100)}% chance of 10cm+). "
                f"Likely range {round(s['p10'])}-{round(s['p90'])} cm.")
        out.append((d["date"], level, title, body))
    return out


def process(summary):
    due = check(summary)
    if not due:
        return
    sent = _load_sent()
    changed = False
    for date, level, title, body in due:
        n, errors = send(title, body, tag=f"snow-{date}")
        for e in errors:
            print("alerts:", e, file=sys.stderr)
        print(f"alerts: {title} -> {n} device(s)")
        if n:
            sent[date] = level
            changed = True
    if changed:
        _save_sent(sent)


if __name__ == "__main__":
    if "--test" in sys.argv:
        n, errors = send("Alagna Snow test", "Notifications are working. You'll get one when a 10cm+ day shows up.",
                         tag="test")
        print(f"test: sent to {n} device(s)", *errors, sep="\n")
        sys.exit(0 if n else 1)
