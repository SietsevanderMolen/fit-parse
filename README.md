# fit-parse

OpenClaw-compatible skill for parsing and summarizing exercise `.fit` files with [`fitdecode`](https://github.com/polyvertex/fitdecode).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python openclaw_fit_skill/fit_summary.py /path/to/activity.fit
```

Default output is detailed JSON (LLM-friendly coach view). Use `--summary` for compact text.

Coach-level detail (compact, interval-based):

```bash
python openclaw_fit_skill/fit_summary.py sample.fit --detail-interval 10s
python openclaw_fit_skill/fit_summary.py sample.fit --detail-interval 1m --pretty-json
python openclaw_fit_skill/fit_summary.py sample.fit --detail-interval 10m --pretty-json
python openclaw_fit_skill/fit_summary.py sample.fit --detail-interval 1m --hr-zone-scheme 55-65,65-75,75-85,85-92,92-100 --pretty-json
python openclaw_fit_skill/fit_summary.py sample.fit --detail-interval 1m --hr-zone-mode bpm --hr-zone-scheme 105-124,124-143,143-162,162-175,175-190 --pretty-json
```

`--detail-interval` accepts values like `10s`, `1m`, `10m`.
`--hr-zone-scheme` accepts comma-separated ranges.
Use `--hr-zone-mode percent` for max-HR percentages, or `--hr-zone-mode bpm` for absolute BPM zones.

## Files

- `SKILL.md`: skill instructions and usage
- `openclaw_fit_skill/fit_summary.py`: parser + summary CLI
- `requirements.txt`: dependency list

## Example outputs

Text summary:

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
python openclaw_fit_skill/fit_summary.py workouts/run.fit
```

Compact summary mode:

```bash
python openclaw_fit_skill/fit_summary.py workouts/run.fit --summary
```
