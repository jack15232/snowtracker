# snowtracker: Alagna snow forecaster

7-day probabilistic snow forecast for Alagna Valsesia (Monterosa Ski), per elevation band,
plus live ARPA Piemonte snow depth and the AINEVA avalanche bulletin. Phone app = GitHub Pages PWA.

## How it runs
- `.github/workflows/update.yml` runs every 15 min (best effort). `run.py --auto` fetches
  obs every 30 min, forecasts every 60 min (a run is archived only when the model data changed),
  avalanche every 3 h, then commits `docs/data/summary.json`.
- State + last 3 days of raw responses persist in the Actions cache (`archive/`, gitignored).
- Force a fetch: Actions → update → Run workflow (works from the GitHub mobile app).
- The app reads `summary.json` through the GitHub contents API (no CDN lag), falling back to Pages.

## Method
- Models (Open-Meteo Ensemble API): ECMWF IFS & AIFS, DWD ICON, NOAA GEFS, MeteoSwiss ICON-CH1/CH2.
  Tokens are tried from a candidate list in `snowcast/config.py` (Open-Meteo renamed some in 2026).
- 4 bands (1200/2000/2400/3000 m) requested via `elevation=` so temperature is lapse-rate corrected.
- Own snow calc per member/hour: precip × snow fraction (band vs freezing level; snow line 300 m below FL,
  300 m ramp; temperature fallback) × temperature-based snow-to-liquid ratio.
- Pooled ensemble: equal weight per model, members share it. Models only count for windows they fully cover.
- Flow regime: ECMWF 700 hPa wind direction, precip-weighted per day (S/SW = Alagna stau).

## Local
```
pip install numpy
python3 run.py            # fetch everything, write docs/data/summary.json
python3 run.py --publish  # + git push
python3 tests/test_pipeline.py   # offline tests with synthetic API responses
```

## Next (not built)
- Bias correction vs Bocchetta delle Pisse obs (needs an archive; run on the M5 without SNOWCAST_KEEP_DAYS).
- Telegram `/snow` command via the existing bridge.

Data: Open-Meteo (CC BY 4.0), Arpa Piemonte (CC BY 4.0), AINEVA / EAWS.
