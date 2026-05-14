# fit-parse

OpenClaw-compatible skill for parsing and summarizing exercise `.fit` files with [`fitdecode`](https://github.com/polyvertex/fitdecode).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit
```

## Files

- `SKILL.md`: skill instructions and usage
- `openclaw_fit_skill/fit_summary.py`: parser + summary CLI
- `requirements.txt`: dependency list

## Example outputs

Text summary (default):

```text
Source: workouts/run.fit
Activity: running
Start Time: 2026-05-01T06:30:00+00:00
Duration: moving 0:45:12 | elapsed 0:45:30
Distance: 10.01 km
Speed/Pace: avg 13.30 km/h (4:31 min/km), max 17.90 km/h
Heart Rate: avg 154.2 bpm, max 178 bpm
Laps: 10 | Records: 2741
```

JSON summary:

```bash
python openclaw_fit_skill/fit_summary.py workouts/run.fit --pretty-json
```
