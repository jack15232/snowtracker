"""Fetch Open-Meteo ensembles for every elevation band and parse to arrays.

Parsed form per model:
    {"token": str, "times": np.ndarray[int unix], "bands": {band_id: {var: np.ndarray[members, hours]}}}
"""

import gzip
import hashlib
import json
import re
import time
from datetime import datetime, timezone

import numpy as np

from . import config
from .http import HTTPError, get_json

_MEMBER_RE = re.compile(r"^(?P<var>[a-z0-9_]+?)(?:_member(?P<m>\d+))?$")


def _params(token, variables):
    n = len(config.BANDS)
    return {
        "latitude": ",".join([str(config.LAT)] * n),
        "longitude": ",".join([str(config.LON)] * n),
        "elevation": ",".join(str(b["elev"]) for b in config.BANDS),
        "hourly": ",".join(variables),
        "models": token,
        "forecast_days": config.FORECAST_DAYS + 1,
        "timeformat": "unixtime",
        "timezone": "GMT",
    }


def parse_location(loc, variables, token=None):
    """One location's JSON -> (times, {var: [members, hours]}). Members sorted; control first."""
    hourly = loc.get("hourly") or {}
    times = np.asarray(hourly.get("time", []), dtype=np.int64)
    out = {}
    for var in variables:
        cols = {}
        for key, vals in hourly.items():
            k = key
            if token and k.endswith("_" + token):   # multi-model suffix, if ever present
                k = k[: -len(token) - 1]
            m = _MEMBER_RE.match(k)
            if not m or m.group("var") != var:
                continue
            idx = int(m.group("m") or 0)
            cols[idx] = np.array([np.nan if v is None else v for v in vals], dtype=float)
        if cols:
            arr = np.vstack([cols[i] for i in sorted(cols)])
            if np.isfinite(arr).any():
                out[var] = arr
    return times, out


def fetch_model(model, state):
    """Try each candidate token; return (parsed, raw_json, error_str)."""
    cache = state.setdefault("tokens", {})
    tokens = list(model["tokens"])
    if cache.get(model["id"]) in tokens:
        tokens.remove(cache[model["id"]])
        tokens.insert(0, cache[model["id"]])
    errors = []
    for token in tokens:
        for variables in (config.HOURLY_VARS, config.CORE_VARS):
            try:
                raw = get_json(config.ENSEMBLE_URL, _params(token, variables))
            except HTTPError as e:
                errors.append(f"{token}: {e.status} {e.body[:120]}")
                if e.status == 400 and "model" in e.body.lower():
                    break   # token unknown -> next token
                continue    # maybe a variable was rejected -> retry core vars
            except Exception as e:  # network
                return None, None, f"network: {e}"
            locs = raw if isinstance(raw, list) else [raw]
            if len(locs) != len(config.BANDS):
                errors.append(f"{token}: expected {len(config.BANDS)} locations, got {len(locs)}")
                break
            bands, times = {}, None
            for band, loc in zip(config.BANDS, locs):
                t, vars_ = parse_location(loc, variables, token)
                times = t if times is None else times
                bands[band["id"]] = vars_
            if not any("precipitation" in b for b in bands.values()):
                errors.append(f"{token}: no precipitation data")
                break
            cache[model["id"]] = token
            return {"token": token, "times": times, "bands": bands}, raw, None
    return None, None, "; ".join(errors) or "no token worked"


def fetch_regime():
    """Deterministic 700 hPa wind for the flow-regime flag (best effort)."""
    err = "no 700hPa data"
    for model in ("ecmwf_ifs025", "best_match"):
        try:
            raw = get_json(config.FORECAST_URL, {
                "latitude": config.LAT, "longitude": config.LON,
                "hourly": "wind_direction_700hPa,wind_speed_700hPa,precipitation",
                "models": model, "forecast_days": config.FORECAST_DAYS + 1,
                "timeformat": "unixtime", "timezone": "GMT"})
            h = raw.get("hourly", {})
            if h.get("wind_direction_700hPa"):
                f = lambda k: np.array([np.nan if v is None else v for v in h[k]], dtype=float)
                return {"model": model, "times": np.asarray(h["time"], dtype=np.int64),
                        "dir": f("wind_direction_700hPa"), "speed": f("wind_speed_700hPa"),
                        "precip": f("precipitation")}, raw, None
        except Exception as e:
            err = str(e)
    return None, None, err


def archive(kind, name, raw):
    """Store the raw response gzipped: archive/<kind>/<name>/<UTC stamp>.json.gz"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    d = config.ARCHIVE_DIR / kind / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{stamp}.json.gz"
    with gzip.open(p, "wt") as f:
        json.dump(raw, f)
    return p


def data_signature(parsed):
    """Hash of the numbers, to tell a new model run from the same one re-served."""
    h = hashlib.sha1()
    for b in sorted(parsed["bands"]):
        arr = parsed["bands"][b].get("precipitation")
        if arr is not None:
            h.update(np.nan_to_num(arr).round(2).tobytes())
    return f"{int(parsed['times'][0])}:{h.hexdigest()[:12]}"


def fetch_all(state):
    """Fetch every model. Returns {model_id: parsed}, status list."""
    results, status = {}, []
    now = time.time()
    for model in config.MODELS:
        parsed, raw, err = fetch_model(model, state)
        entry = {"id": model["id"], "name": model["name"], "ok": parsed is not None,
                 "fetched_at": int(now)}
        if parsed is None:
            entry["error"] = err
        else:
            sig = data_signature(parsed)
            prev = state.setdefault("signatures", {}).get(model["id"])
            entry["token"] = parsed["token"]
            entry["new_run"] = sig != prev
            if sig != prev:
                archive("ensemble", model["id"], raw)
                state["signatures"][model["id"]] = sig
                state.setdefault("run_seen_at", {})[model["id"]] = int(now)
            entry["run_seen_at"] = state.get("run_seen_at", {}).get(model["id"])
            entry["members"] = int(next(iter(parsed["bands"].values()))["precipitation"].shape[0])
            valid = np.isfinite(next(iter(parsed["bands"].values()))["precipitation"]).any(axis=0)
            entry["horizon_h"] = int(valid.sum())
            results[model["id"]] = parsed
        status.append(entry)
    return results, status
