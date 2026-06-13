# Orbit Wars Agent Variants

`main.py` is the active Kaggle submission file.

Known snapshots:

- `stable_540.py` — safest historical branch, roughly 520-540 rating band.
- `v21_global_planner.py` — first structural global-planner experiment.

Use a variant:

```powershell
python tools\use_variant.py agents\v21_global_planner.py
```

Evaluate when `kaggle_environments` is installed:

```powershell
python tools\evaluate_orbit.py --agent main.py --opponent agents\stable_540.py --games 50 --seed 1000 --save-replays
```

Submission rule: submit only `main.py` unless intentionally creating a multi-file archive.
