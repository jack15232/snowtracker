"""ARPA Piemonte live station data + AINEVA/EAWS avalanche bulletin."""

import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config
from .forecast import archive
from .http import HTTPError, get_json

ATTRIBUTION = "Fonte: Arpa Piemonte (CC BY 4.0)"


def _series(param, sensor):
    """ARPA geojson -> sorted [(unix, value)] of validated-OK readings. Times are UTC."""
    raw = get_json(config.ARPA_SERIES_URL.format(param=param, sensor=sensor))
    readings = raw.get("properties", {}).get(param, {}) or {}
    out = []
    for stamp, rec in readings.items():
        v = rec.get("value") if isinstance(rec, dict) else rec
        if v is None or (isinstance(rec, dict) and rec.get("valid_type") not in (None, "OK")):
            continue
        t = datetime.strptime(stamp[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        out.append((int(t.timestamp()), float(v)))
    return sorted(out), raw


def _change(series, hours):
    if not series:
        return None
    t_last, v_last = series[-1]
    past = [v for t, v in series if t <= t_last - hours * 3600]
    return round(v_last - past[-1], 1) if past else None


def fetch_stations():
    out = []
    for st in config.STATIONS:
        rec = {**st, "ok": False}
        try:
            hs, raw = _series("nivo", st["sensor"])
            archive("obs", st["sensor"], raw)
            if hs:
                rec.update(ok=True, hs_cm=hs[-1][1], hs_time=hs[-1][0],
                           d24=_change(hs, 24), d72=_change(hs, 72),
                           series=[[t, v] for t, v in hs[-168:]])
            else:
                rec["error"] = "no valid readings"
            try:
                ta, _ = _series("terma", st["sensor"])
                if ta:
                    rec["temp_c"], rec["temp_time"] = ta[-1][1], ta[-1][0]
            except Exception:
                pass
        except Exception as e:
            rec["error"] = str(e)[:200]
        out.append(rec)
    return {"stations": out, "fetched_at": int(time.time()), "attribution": ATTRIBUTION}


def _ratings_text(ratings):
    parts = []
    for r in ratings or []:
        el = r.get("elevation") or {}
        where = (f"above {el['lowerBound']}m" if "lowerBound" in el else
                 f"below {el['upperBound']}m" if "upperBound" in el else "all elevations")
        when = r.get("validTimePeriod")
        parts.append({"level": r.get("mainValue"), "where": where,
                      "period": when if when in ("earlier", "later") else None})
    return parts


LEVELS = {"low": 1, "moderate": 2, "considerable": 3, "high": 4, "very_high": 5}


def fetch_avalanche():
    tz = ZoneInfo(config.TZ)
    today = datetime.now(tz).date()
    out = {"region": config.AVALANCHE_REGION, "days": [], "fetched_at": int(time.time()),
           "attribution": "Fonte: AINEVA Piemonte / EAWS"}
    for d in (today, today + timedelta(days=1)):
        ds = d.strftime("%Y-%m-%d")
        try:
            raw = get_json(config.EAWS_URL.format(d=ds))
        except HTTPError as e:
            if e.status == 404:
                out["days"].append({"date": ds, "published": False})
                continue
            out["days"].append({"date": ds, "published": False, "error": str(e)[:150]})
            continue
        except Exception as e:
            out["days"].append({"date": ds, "published": False, "error": str(e)[:150]})
            continue
        archive("avalanche", ds, raw)
        hit = None
        for b in raw.get("bulletins", []):
            if any(r.get("regionID") == config.AVALANCHE_REGION for r in b.get("regions", [])):
                hit = b
                break
        if not hit:
            out["days"].append({"date": ds, "published": True, "region_found": False})
            continue
        ratings = _ratings_text(hit.get("dangerRatings"))
        out["days"].append({
            "date": ds, "published": True, "region_found": True,
            "max_level": max((LEVELS.get(r["level"], 0) for r in ratings), default=0),
            "ratings": ratings,
            "problems": [{"type": p.get("problemType"), "aspects": p.get("aspects"),
                          "elevation": p.get("elevation")} for p in hit.get("avalancheProblems", [])],
            "highlights": (hit.get("avalancheActivity") or {}).get("highlights"),
            "published_at": hit.get("publicationTime"),
        })
    return out


def probe_webcams():
    """Check each webcam image is reachable and how fresh it is (Last-Modified)."""
    import urllib.request
    from email.utils import parsedate_to_datetime
    out = []
    for cam in config.WEBCAMS:
        url = config.WEBCAM_BASE + cam["path"]
        rec = {k: cam[k] for k in ("id", "name", "elev", "page")}
        rec.update(url=url, ok=False)
        try:
            req = urllib.request.Request(url, method="GET", headers={
                "User-Agent": config.USER_AGENT, "Range": "bytes=0-2047",
                "Referer": "https://monterosaski.eu/"})
            with urllib.request.urlopen(req, timeout=15) as r:
                ctype = r.headers.get("Content-Type", "")
                lm = r.headers.get("Last-Modified")
                head = r.read(4)
            rec["ok"] = ctype.startswith("image/") or head[:3] == b"\xff\xd8\xff"
            if lm:
                rec["updated"] = int(parsedate_to_datetime(lm).timestamp())
            if not rec["ok"]:
                rec["error"] = f"not an image ({ctype})"
        except Exception as e:
            rec["error"] = str(e)[:120]
        out.append(rec)
    return {"cams": out, "checked_at": int(time.time()), "index": config.WEBCAM_INDEX,
            "attribution": "Webcams: Monterosa Ski / monterosa2000.it"}
