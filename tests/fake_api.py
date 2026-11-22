"""Synthetic Open-Meteo / ARPA / EAWS responses in the real wire formats, for offline tests."""

import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

FIX = Path(__file__).parent / "fixtures"
HORIZON = {"ecmwf_ifs025_ensemble": 192, "ecmwf_aifs025_ensemble": 192, "icon_seamless_eps": 180,
           "ncep_gefs025": 192, "meteoswiss_icon_ch2_ensemble": 120, "meteoswiss_icon_ch1_ensemble": 33}
MEMBERS = {"ecmwf_ifs025_ensemble": 50, "ecmwf_aifs025_ensemble": 50, "icon_seamless_eps": 39,
           "ncep_gefs025": 30, "meteoswiss_icon_ch2_ensemble": 20, "meteoswiss_icon_ch1_ensemble": 10}
NOW = int(time.time()) // 3600 * 3600


def ensemble(q):
    token = q["models"][0]
    if token not in HORIZON:
        from snowcast.http import HTTPError
        raise HTTPError("fake", 400, '{"error":true,"reason":"Invalid model"}')
    elevs = [float(e) for e in q["elevation"][0].split(",")]
    variables = q["hourly"][0].split(",")
    start = NOW - (NOW % 86400)
    n = (int(q["forecast_days"][0])) * 24
    times = [start + 3600 * i for i in range(n)]
    rng = np.random.default_rng(abs(hash(token)) % 2**32)
    hz, nm = HORIZON[token], MEMBERS[token]
    bias = {"ncep_gefs025": 1.3, "icon_seamless_eps": 0.8}.get(token, 1.0)
    member_series = []
    for m in range(nm + 1):
        shift = rng.normal(0, 4)          # timing error (h)
        amp = rng.lognormal(0, 0.35) * bias
        h = np.arange(n) - (NOW - start) / 3600
        storm = 1.8 * amp * np.exp(-0.5 * ((h - 40 - shift) / 7) ** 2)
        storm2 = 1.0 * amp * np.exp(-0.5 * ((h - 120 - shift * 2) / 10) ** 2)
        precip = np.maximum(storm + storm2 + rng.normal(0, 0.05, n), 0)
        fl = 2600 - 1200 * np.exp(-0.5 * ((h - 45 - shift) / 15) ** 2) + rng.normal(0, 80, n) - 200 * np.sin(h / 12)
        member_series.append((precip, fl))
    locs = []
    for e in elevs:
        hourly = {"time": times}
        for m, (precip, fl) in enumerate(member_series):
            t2m = (fl - e) * 0.0065 + rng.normal(0, 0.3, n)
            vals = {"precipitation": precip, "temperature_2m": t2m, "freezing_level_height": fl,
                    "snowfall": precip * (t2m < 1) * 0.7}
            for v in variables:
                arr = vals[v].round(2).tolist()
                arr = [None if i >= hz else x for i, x in enumerate(arr)]
                hourly[v if m == 0 else f"{v}_member{m:02d}"] = arr
        locs.append({"latitude": 45.85, "longitude": 7.94, "elevation": e, "hourly": hourly})
    return locs if len(locs) > 1 else locs[0]


def regime(q):
    start = NOW - (NOW % 86400)
    n = int(q["forecast_days"][0]) * 24
    h = np.arange(n) - (NOW - start) / 3600
    d = np.where(h < 80, 200.0, 330.0)
    p = 1.5 * np.exp(-0.5 * ((h - 40) / 7) ** 2) + np.exp(-0.5 * ((h - 120) / 10) ** 2)
    return {"hourly": {"time": [start + 3600 * i for i in range(n)], "wind_direction_700hPa": d.tolist(),
                       "wind_speed_700hPa": [40.0] * n, "precipitation": p.round(2).tolist()}}


def arpa(url):
    sensor = url.rsplit("/", 1)[-1].split(".")[0]
    param = url.rsplit("/", 2)[-2]
    base = json.loads((FIX / "nivo_001019900.geojson").read_text())
    props = base["properties"]
    readings = {}
    for i in range(144):
        t = time.gmtime(NOW - (143 - i) * 3600)
        v = (40 + i * 0.1 + (12 if i > 120 else 0)) if param == "nivo" else -4.0
        readings[time.strftime("%Y-%m-%dT%H:%M", t)] = {"value": v, "valid_type": "OK", "flag_type": "0"}
    props.pop("nivo", None)
    props[param] = readings
    props["sensor"] = sensor
    return base


def eaws(url):
    from snowcast.http import HTTPError
    raise HTTPError(url, 404, "Not Found")


def fake_get_json(url, params=None, **kw):
    q = {k: [str(v)] for k, v in (params or {}).items()}
    if "ensemble-api" in url:
        return ensemble(q)
    if "api.open-meteo.com" in url:
        return regime(q)
    if "arpa.piemonte.it" in url:
        return arpa(url)
    if "avalanche.report" in url:
        return eaws(url)
    raise AssertionError(url)
