"""Turn parsed model data into the summary.json the phone app reads."""

import math
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from . import config
from .snowcalc import snow_cm, weighted_prob, weighted_quantiles

TZ = ZoneInfo(config.TZ)
QS = [0.1, 0.25, 0.5, 0.75, 0.9]


def _r(x, nd=1):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, nd)


def windows(now):
    """Today (rest of) + following days, as (label, t0, t1] in unix seconds, local days."""
    local = datetime.fromtimestamp(now, TZ)
    start_hour = local.replace(minute=0, second=0, microsecond=0)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for d in range(config.FORECAST_DAYS):
        day0 = midnight + timedelta(days=d)
        day1 = midnight + timedelta(days=d + 1)
        t0 = start_hour if d == 0 else day0
        out.append({"date": day0.strftime("%Y-%m-%d"), "dow": day0.strftime("%a"),
                    "partial_from": start_hour.strftime("%H:%M") if d == 0 else None,
                    "t0": int(t0.timestamp()), "t1": int(day1.timestamp())})
    return out


def _window_idx(times, t0, t1):
    """Indices of hourly accumulations ending in (t0, t1]; None if not fully covered."""
    idx = np.where((times > t0) & (times <= t1))[0]
    return idx if len(idx) == (t1 - t0) // 3600 else None


def _model_snow(parsed, band):
    v = parsed["bands"].get(band["id"], {})
    if "precipitation" not in v:
        return None, None
    snow = snow_cm(v["precipitation"], v.get("temperature_2m"), v.get("freezing_level_height"), band["elev"])
    raw = v.get("snowfall")
    return snow, raw


def _pool(per_model):
    """per_model: {model_id: member values} -> (values, weights) with equal weight per model."""
    vals, wts = [], []
    for mid, arr in per_model.items():
        arr = np.asarray(arr, float)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            continue
        vals.append(arr)
        wts.append(np.full(arr.size, config.MODEL_WEIGHTS.get(mid, 1.0) / arr.size))
    if not vals:
        return np.array([]), np.array([])
    return np.concatenate(vals), np.concatenate(wts)


def _window_totals(results, band, t0, t1, var="snow"):
    """{model_id: per-member totals over the window} for models covering it fully."""
    out = {}
    for mid, parsed in results.items():
        snow, raw = _model_snow(parsed, band)
        arr = snow if var == "snow" else raw
        if arr is None:
            continue
        idx = _window_idx(parsed["times"], t0, t1)
        if idx is None:
            continue
        sub = arr[:, idx]
        good = np.isfinite(sub).all(axis=1)
        if good.any():
            out[mid] = sub[good].sum(axis=1)
    return out


def _stats(per_model, thresholds):
    vals, wts = _pool(per_model)
    if vals.size == 0:
        return None
    q = weighted_quantiles(vals, wts, QS)
    s = {"p10": _r(q[0]), "p25": _r(q[1]), "p50": _r(q[2]), "p75": _r(q[3]), "p90": _r(q[4]),
         "models": sorted(per_model)}
    for th in thresholds:
        s[f"p_gt{th}"] = _r(weighted_prob(vals, wts, th), 2)
    s["by_model"] = {m: _r(float(np.median(v))) for m, v in per_model.items()}
    return s


def agreement(by_model, pooled_median):
    meds = [v for v in by_model.values() if v is not None]
    if len(meds) < 2 or pooled_median is None:
        return "n/a"
    spread = max(meds) - min(meds)
    if spread <= max(5, 0.35 * pooled_median):
        return "good"
    if spread <= max(10, 0.7 * pooled_median):
        return "mixed"
    return "poor"


def regime_for(regime, t0, t1):
    if not regime:
        return None
    t = regime["times"]
    m = (t > t0) & (t <= t1) & np.isfinite(regime["dir"]) & np.isfinite(regime["precip"])
    p = regime["precip"][m]
    if p.sum() < 1.0:
        return {"code": "dry", "label": "Mostly dry", "precip_mm": _r(float(p.sum()))}
    w = p
    rad = np.deg2rad(regime["dir"][m])
    d = (np.rad2deg(np.arctan2((w * np.sin(rad)).sum(), (w * np.cos(rad)).sum())) + 360) % 360
    if 135 <= d < 247.5:
        code, label = "south", "S/SW flow: Alagna side favoured"
    elif 247.5 <= d < 292.5:
        code, label = "west", "Westerly: mixed, north side often favoured"
    elif d >= 292.5 or d < 45:
        code, label = "north", "Northerly: Alagna sheltered (north foehn)"
    else:
        code, label = "east", "Easterly/SE: Piedmont side can do well"
    return {"code": code, "label": label, "dir_deg": int(round(d)), "precip_mm": _r(float(p.sum()))}


def freezing_level(results, now):
    """Hourly pooled FL quantiles for the next FORECAST_DAYS (band-independent)."""
    band = config.BANDS[0]["id"]
    hours = np.arange((now // 3600 + 1) * 3600, now + config.FORECAST_DAYS * 86400, 3600)
    out = []
    for h in hours[::1]:
        per = {}
        for mid, parsed in results.items():
            fl = parsed["bands"].get(band, {}).get("freezing_level_height")
            if fl is None:
                continue
            i = np.where(parsed["times"] == h)[0]
            if len(i):
                col = fl[:, i[0]]
                if np.isfinite(col).any():
                    per[mid] = col
        vals, wts = _pool(per)
        if vals.size:
            q = weighted_quantiles(vals, wts, [0.1, 0.5, 0.9])
            out.append([int(h), int(q[0]), int(q[1]), int(q[2])])
    return out


def blocks(results, band, now, hours=72, step=3):
    start = (now // 3600) * 3600
    out = []
    for t0 in range(start, start + hours * 3600, step * 3600):
        st = _stats(_window_totals(results, band, t0, t0 + step * 3600), [])
        if st:
            out.append({"t0": t0, "p50": st["p50"], "p90": st["p90"]})
    return out


def build(results, status, regime, obs, avalanche, now=None):
    now = int(now or time.time())
    wins = windows(now)
    bands_out = {}
    for band in config.BANDS:
        days = []
        for w in wins:
            st = _stats(_window_totals(results, band, w["t0"], w["t1"]), config.PROB_THRESHOLDS_CM)
            raw = _stats(_window_totals(results, band, w["t0"], w["t1"], var="raw"), [])
            day = {k: w[k] for k in ("date", "dow", "partial_from")}
            day["snow"] = st
            day["raw_model_p50"] = raw["p50"] if raw else None
            days.append(day)
        start = (now // 3600) * 3600
        h72 = _stats(_window_totals(results, band, start, start + 72 * 3600), [config.HEADLINE_THRESHOLD_CM])
        d7 = _stats(_window_totals(results, band, wins[0]["t0"], wins[-1]["t1"]), [config.HEADLINE_THRESHOLD_CM])
        if h72:
            h72["agreement"] = agreement(h72["by_model"], h72["p50"])
        bands_out[band["id"]] = {"label": band["label"], "elev": band["elev"], "days": days,
                                 "next72h": h72, "next7d": d7, "blocks3h": blocks(results, band, now)}
    regimes = [regime_for(regime, w["t0"], w["t1"]) for w in wins]
    for b in bands_out.values():
        for d, r in zip(b["days"], regimes):
            d["regime"] = r
    return {
        "generated_at": now,
        "tz": config.TZ,
        "location": {"name": "Alagna Valsesia", "lat": config.LAT, "lon": config.LON},
        "headline_band": config.HEADLINE_BAND,
        "bands": bands_out,
        "freezing_level": freezing_level(results, now) if results else [],
        "models": status,
        "regime_model": regime["model"] if regime else None,
        "obs": obs,
        "avalanche": avalanche,
        "method": {
            "snow": "Own calc: ensemble precip x snow fraction (band elevation vs freezing level, "
                    f"snow line {config.SNOWLINE_BELOW_FL_M} m below FL) x temperature-based SLR. "
                    "Models weighted equally; members share their model's weight.",
            "raw_model": "Open-Meteo native snowfall at the gridpoint (no elevation correction).",
        },
    }
