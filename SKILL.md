# OpenClaw Skill: FIT Exercise Summary

This skill reads `.fit` activity files with [`fitdecode`](https://github.com/polyvertex/fitdecode) and generates a detailed exercise summary.

## What it does

- Parses FIT records, sessions, laps, and event messages
- Aggregates core workout metrics:
  - Start time, elapsed/moving duration
  - Distance, average/max speed, pace
  - Heart rate average/max
  - Power average/max (if present)
  - Cadence average/max (if present)
  - Elevation gain/loss
  - Temperature, calories
- Produces:
  - Human-readable report
  - JSON summary for downstream automation

## Usage

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run summary:

```bash
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit
```

Default output is detailed JSON. Use compact text mode:

```bash
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit --summary
```

JSON output:

```bash
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit --pretty-json
```

Higher-detail coach summary:

```bash
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit --detail-interval 10s --pretty-json
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit --detail-interval 1m --pretty-json
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit --detail-interval 10m --pretty-json
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit --detail-interval 1m --hr-zone-scheme 55-65,65-75,75-85,85-92,92-100 --pretty-json
```

`--detail-interval` values are compact buckets (`<N>s` or `<N>m`) to keep output LLM-friendly.
`--hr-zone-scheme` sets custom HR zones as max-HR percentages (comma-separated ranges).

## Inputs

- A single `.fit` file path.

## Outputs

- Detailed JSON document (default)
- Compact text report (`--summary`)
- Includes coach-detail blocks:
  - interval metrics (HR/speed/power/cadence per bucket)
  - HR zone distribution
  - 1km split trend

## Notes

- FIT files vary by device and sport; some fields may be unavailable.
- The parser falls back to record-derived values when session aggregates are missing.
