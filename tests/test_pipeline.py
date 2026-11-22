"""Offline tests: python3 -m pytest tests  (or python3 tests/test_pipeline.py)"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from snowcast import config, snowcalc  # noqa: E402


def test_snow_fraction():
    fl = np.array([2500.0, 2500.0, 2500.0, np.nan, np.nan])
    t = np.array([0.0, 0.0, 0.0, -2.0, 3.0])
    elev = np.array([3000, 2200, 1500, 2000, 2000])
    f = snowcalc.snow_fraction(elev, fl, t)
    assert f[0] == 1.0            # above FL
    assert 0 < f[1] <= 1.0        # 300 m below FL = snow line -> mostly snow
    assert f[2] == 0.0            # far below
    assert f[3] == 1.0 and f[4] == 0.0   # temperature fallback


def test_slr_monotonic():
    s = snowcalc.slr(np.array([-15, -6, 0, 2]))
    assert list(s) == sorted(s, reverse=True)


def test_weighted_quantiles():
    v = np.r_[np.zeros(50), np.ones(10) * 10]
    w = np.r_[np.full(50, 0.5 / 50), np.full(10, 0.5 / 10)]   # two models, equal weight
    assert abs(snowcalc.weighted_prob(v, w, 5) - 0.5) < 1e-9


def test_end_to_end(tmp_path=None):
    import fake_api
    from snowcast import forecast, http, obs
    tmp = Path(tmp_path or "/tmp/snowcast_test")
    config.ARCHIVE_DIR = tmp / "archive"
    config.STATE_FILE = tmp / "archive" / "state.json"
    config.DATA_DIR = tmp / "data"
    for mod in (http, forecast, obs):
        mod.get_json = fake_api.fake_get_json
    import run
    run.forecast.get_json = fake_api.fake_get_json
    sys.argv = ["run.py"]
    run.main()
    s = json.loads((config.DATA_DIR / "summary.json").read_text())
    ok = [m["id"] for m in s["models"] if m["ok"]]
    assert len(ok) == len(config.MODELS), s["models"]
    b = s["bands"]
    # more snow up high than in the village
    assert b["3000"]["next7d"]["p50"] > b["1200"]["next7d"]["p50"]
    # CH1 (33 h) must not appear in day-3+ totals
    assert "ch1" not in b["2400"]["days"][3]["snow"]["models"]
    assert s["obs"]["stations"][0]["ok"] and s["obs"]["stations"][0]["d24"] is not None
    assert s["avalanche"]["days"][0]["published"] is False
    assert len(s["freezing_level"]) > 100
    assert s["bands"]["2400"]["days"][1]["regime"]["code"] in ("south", "dry", "north", "west", "east")
    # second run: same data -> no new archive files
    n_before = len(list((config.ARCHIVE_DIR / "ensemble").rglob("*.gz")))
    run.main()
    assert len(list((config.ARCHIVE_DIR / "ensemble").rglob("*.gz"))) == n_before
    return s


if __name__ == "__main__":
    test_snow_fraction(); test_slr_monotonic(); test_weighted_quantiles()
    s = test_end_to_end()
    print(json.dumps(s["bands"]["2400"]["next72h"], indent=1))
    print("all tests passed")
