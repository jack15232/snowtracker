#!/usr/bin/env python3
"""snowcast runner.

  python3 run.py              fetch everything, rebuild summary
  python3 run.py --auto       only fetch what is due (for launchd, every 15 min)
  python3 run.py --publish    also git commit + push docs/data to GitHub Pages
  python3 run.py --offline    rebuild summary from the latest archived responses
"""

import argparse
import gzip
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from snowcast import config, forecast, obs, summary  # noqa: E402
from snowcast.forecast import parse_location  # noqa: E402


def load_state():
    try:
        return json.loads(config.STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state):
    config.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.STATE_FILE.write_text(json.dumps(state, indent=1))


def due(state, key, minutes):
    return time.time() - state.get("last", {}).get(key, 0) >= minutes * 60 - 30


def mark(state, key):
    state.setdefault("last", {})[key] = int(time.time())


def latest_archive(kind, name):
    d = config.ARCHIVE_DIR / kind / name
    files = sorted(d.glob("*.json.gz")) if d.exists() else []
    if not files:
        return None
    with gzip.open(files[-1], "rt") as f:
        return json.load(f)


def parsed_from_archive(model, state):
    raw = latest_archive("ensemble", model["id"])
    if raw is None:
        return None
    locs = raw if isinstance(raw, list) else [raw]
    token = state.get("tokens", {}).get(model["id"])
    bands, times = {}, None
    for band, loc in zip(config.BANDS, locs):
        t, v = parse_location(loc, config.HOURLY_VARS, token)
        times = t if times is None else times
        bands[band["id"]] = v
    return {"token": token, "times": times, "bands": bands}


def prune_archive():
    """Optional: keep only the last N days of raw responses (set SNOWCAST_KEEP_DAYS)."""
    import os
    days = os.environ.get("SNOWCAST_KEEP_DAYS")
    if not days:
        return
    cutoff = time.time() - float(days) * 86400
    for kind in ("ensemble", "obs", "regime", "avalanche"):
        d = config.ARCHIVE_DIR / kind
        if not d.exists():
            continue
        for sub in d.iterdir():
            files = sorted(sub.glob("*.json.gz"))
            for f in files[:-1]:   # always keep the newest file per source
                if f.stat().st_mtime < cutoff:
                    f.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--only", choices=["obs", "forecast"], help="force just one part")
    a = ap.parse_args()

    state = load_state()
    cache_path = config.ARCHIVE_DIR / "last_parts.json"
    try:
        parts = json.loads(cache_path.read_text())
    except Exception:
        parts = {}

    do_fc = not a.offline and (a.only in (None, "forecast")) and (not a.auto or due(state, "forecast", config.FORECAST_EVERY_MIN))
    do_obs = not a.offline and (a.only in (None, "obs")) and (not a.auto or due(state, "obs", config.OBS_EVERY_MIN))
    do_av = not a.offline and a.only is None and (not a.auto or due(state, "avalanche", config.AVALANCHE_EVERY_MIN))

    if a.auto and not (do_fc or do_obs or do_av):
        print("nothing due")
        return
    prune_archive()

    if do_fc:
        results, status = forecast.fetch_all(state)
        # a model that failed this time falls back to its last archived run
        for st in status:
            if not st["ok"]:
                m = next(m for m in config.MODELS if m["id"] == st["id"])
                p = parsed_from_archive(m, state)
                if p is not None and p["times"] is not None and len(p["times"]):
                    results[m["id"]] = p
                    st["using_archived"] = True
        reg, reg_raw, reg_err = forecast.fetch_regime()
        if reg_raw:
            forecast.archive("regime", "ecmwf700", reg_raw)
        parts["status"] = status
        parts["regime_error"] = reg_err
        mark(state, "forecast")
    else:
        results = {}
        for m in config.MODELS:
            p = parsed_from_archive(m, state)
            if p is not None and p["times"] is not None and len(p["times"]):
                results[m["id"]] = p
        reg = None
        raw = latest_archive("regime", "ecmwf700")
        if raw:
            import numpy as np
            h = raw["hourly"]
            f = lambda k: np.array([np.nan if v is None else v for v in h[k]], dtype=float)
            reg = {"model": "archived", "times": np.asarray(h["time"], dtype=np.int64),
                   "dir": f("wind_direction_700hPa"), "speed": f("wind_speed_700hPa"),
                   "precip": f("precipitation")}

    if do_obs:
        parts["obs"] = obs.fetch_stations()
        try:
            parts["webcams"] = obs.probe_webcams()
        except Exception as e:
            print("webcam probe failed:", e, file=sys.stderr)
        mark(state, "obs")
    if do_av:
        parts["avalanche"] = obs.fetch_avalanche()
        mark(state, "avalanche")

    if not results:
        print("No forecast data yet (no successful fetch and nothing archived).", file=sys.stderr)

    out = summary.build(results, parts.get("status", []), reg, parts.get("obs"), parts.get("avalanche"))
    out["regime_error"] = parts.get("regime_error")
    out["webcams"] = parts.get("webcams")
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "summary.json").write_text(json.dumps(out, separators=(",", ":")))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(parts))
    save_state(state)

    h = out["bands"][config.HEADLINE_BAND]["next72h"]
    ok = [s["name"] for s in parts.get("status", []) if s.get("ok")]
    print(f"models ok: {ok}  |  2400m next 72h: "
          + (f"{h['p50']} cm (P10-P90 {h['p10']}-{h['p90']}), P(>20cm)={h['p_gt20']}" if h else "n/a"))

    if a.publish:
        from publish import publish
        publish()


if __name__ == "__main__":
    main()
