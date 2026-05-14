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

JSON output:

```bash
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit --pretty-json
```

## Inputs

- A single `.fit` file path.

## Outputs

- Text report (default)
- JSON document (`--json` or `--pretty-json`)

## Notes

- FIT files vary by device and sport; some fields may be unavailable.
- The parser falls back to record-derived values when session aggregates are missing.
