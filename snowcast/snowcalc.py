"""Elevation-aware snowfall from ensemble precip, temperature and freezing level."""

import numpy as np

from . import config


def snow_fraction(elev, fl, t2m):
    """Fraction of precip falling as snow at `elev` (m). Arrays broadcast.

    Primary: band elevation vs freezing level. Snow line ~SNOWLINE_BELOW_FL_M below FL,
    linear ramp of SNOW_RAMP_M centred on it. Fallback where FL is missing: band temperature.
    """
    snowline = fl - config.SNOWLINE_BELOW_FL_M
    half = config.SNOW_RAMP_M / 2
    frac_fl = np.clip((elev - (snowline - half)) / config.SNOW_RAMP_M, 0, 1)
    frac_t = np.clip((config.T_ALL_RAIN - t2m) / (config.T_ALL_RAIN - config.T_ALL_SNOW), 0, 1)
    out = np.where(np.isfinite(fl), frac_fl, frac_t)
    # Belt and braces: it does not snow at +4°C even if FL is reported oddly high/low.
    out = np.where(np.isfinite(t2m) & (t2m >= 4.0), 0.0, out)
    out = np.where(np.isfinite(t2m) & (t2m <= -3.0), 1.0, out)
    return out


def slr(t2m):
    """Snow-to-liquid ratio from band temperature (°C)."""
    xs, ys = zip(*config.SLR_TABLE)
    return np.interp(np.nan_to_num(t2m, nan=0.0), xs, ys)


def snow_cm(precip_mm, t2m, fl, elev):
    """Hourly new snow (cm) at `elev`. Inputs shaped [members, hours]."""
    fl = fl if fl is not None else np.full_like(precip_mm, np.nan)
    t2m = t2m if t2m is not None else np.full_like(precip_mm, np.nan)
    frac = snow_fraction(elev, fl, t2m)
    return precip_mm * frac * slr(t2m) / 10.0


def weighted_quantiles(values, weights, qs):
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    ok = np.isfinite(values)
    values, weights = values[ok], weights[ok]
    if values.size == 0:
        return [None] * len(qs)
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cw = np.cumsum(w) - 0.5 * w
    cw /= w.sum()
    return [float(np.interp(q, cw, v)) for q in qs]


def weighted_prob(values, weights, threshold):
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    ok = np.isfinite(values)
    if not ok.any():
        return None
    return float((weights[ok] * (values[ok] > threshold)).sum() / weights[ok].sum())
