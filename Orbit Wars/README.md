# Orbit Wars Kaggle Agent

This repository contains a Python agent for **Orbit Wars**, a Kaggle simulation competition where submitted bots play a real-time strategy game against other agents on the leaderboard.

Orbit Wars is inspired by the classic 2010 Planet Wars challenge. Players command fleets, capture planets, defend territory, and try to finish each episode with the highest total ship count.

## Competition Overview

- **Competition:** Orbit Wars
- **Platform:** Kaggle Competitions / Kaggle Environments
- **Sponsor:** Google LLC
- **Start Date:** April 16, 2026
- **Entry & Team Merger Deadline:** June 16, 2026
- **Final Submission Deadline:** June 23, 2026
- **Final Evaluation Window:** Approximately June 24, 2026 to July 8, 2026
- **Prize Pool:** $50,000 total, split evenly across the top 10 places

The competition evaluates agents by running repeated episodes against other bots with similar skill ratings. Ratings are modeled with a Gaussian skill estimate, and bots gain or lose rating based on wins, losses, or draws.

## Game Summary

Orbit Wars is played on a continuous `100 x 100` board with a sun at the center. Fleets that cross the sun are destroyed.

Each player starts with one home planet and competes to capture neutral and enemy planets. Planets produce ships every turn, and owned ships can be launched as fleets toward other planets.

Key mechanics:

- **Planets** have ownership, position, radius, ship count, and production value.
- **Orbiting planets** rotate around the sun during the game.
- **Static planets** remain fixed.
- **Fleets** travel in straight lines, with larger fleets moving faster.
- **Comets** spawn during the game as temporary capturable planets.
- **Combat** resolves when fleets collide with planets.
- **Episodes** last up to 500 turns.
- **Winner** is the player with the highest total ships on planets and in fleets, or the last surviving player.

## Submission Format

Kaggle accepts either:

- A single Python file with an agent function.
- A compressed archive containing `main.py` at the top level.

This repository uses the archive format because the agent depends on helper modules in `orbit_lite/`.

The expected entry point is:

```python
def agent(obs):
    ...
    return [[from_planet_id, angle_in_radians, num_ships], ...]
```

## Repository Structure

```text
.
|-- main.py                         # Kaggle agent entry point
|-- orbit_lite/                     # Planner, movement, geometry, and adapter helpers
|-- agents/                         # Older experimental agents and baselines
|-- tools/                          # Local analysis / helper scripts
|-- run_local.py                    # Local environment runner
|-- replay.json                     # Latest downloaded replay for analysis
|-- 0_log.json / 1_log.json         # Latest downloaded player logs
|-- submission_exp48.tar.gz         # Top submission — leaderboard score 1211
`-- submission_exp48_*.tar.gz       # Later experimental submission archives
```

## Current Agent Approach

The main agent is a lightweight production-and-capture planner. At each turn, it:

1. Parses the Kaggle observation into tensors.
2. Predicts planet movement and near-future garrison states.
3. Builds a shortlist of attack and defense targets.
4. Scores possible fleet launches by projected net ship gain.
5. Greedily selects valid launches under source-budget constraints.
6. Optionally regroups ships toward pressured friendly planets.
7. Converts selected launches back into Kaggle action format.

The agent is designed to run within Kaggle's per-turn timeout and avoid external network access during evaluation.

## Local Setup

Install Kaggle Environments:

```bash
pip install "kaggle-environments>=1.28.0"
```

Some versions of this agent also rely on PyTorch:

```bash
pip install torch
```

Run a local match:

```bash
python run_local.py
```

Or from Python:

```python
from kaggle_environments import make

env = make("orbit_wars", configuration={"seed": 42}, debug=True)
env.run(["main.py", "random"])

for i, state in enumerate(env.steps[-1]):
    print(f"Player {i}: reward={state.reward}, status={state.status}")
```

## Building a Submission Archive

Create a Kaggle-ready archive with `main.py` and `orbit_lite/` at the archive root:

```bash
python - <<'PY'
import tarfile
from pathlib import Path

out = Path("submission.tar.gz")
with tarfile.open(out, "w:gz") as tar:
    tar.add("main.py", arcname="main.py")
    for path in sorted(Path("orbit_lite").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            tar.add(path, arcname=path.as_posix())

print(out)
PY
```

Submit on Kaggle using the web upload dialog or Kaggle CLI:

```bash
kaggle competitions submit orbit-wars -f submission.tar.gz -m "agent update"
```

## Replay Analysis Workflow

After submitting, Kaggle provides validation and ladder episodes. Download the replay and player logs, then overwrite:

- `replay.json`
- `0_log.json`
- `1_log.json`
- `2_log.json`
- `3_log.json`

The replay can be inspected to compare:

- Planet count over time.
- Production controlled by each player.
- Fleet launch volume.
- Key ownership flips.
- Elimination timing.
- Whether failures are caused by runtime errors, under-expansion, over-extension, or weak defense.

## Competition Compliance Notes

Important rules followed by this repository:

- Submissions must not use network ingress or egress during evaluation.
- Private code sharing outside a Kaggle team is not allowed.
- Publicly shared competition code should be shared through Kaggle forums or notebooks under an OSI-approved license.
- External data and tools must be publicly accessible and reasonably available to all participants.
- Winning submissions must be reproducible and licensed according to the competition rules.

If this agent places in the prize range, the methodology, code, setup instructions, and any relevant hyperparameters should be documented clearly enough for reproduction.

## Status

The strongest submitted branch is the `exp48` / `orbit_lite` planner family (`submission_exp48.tar.gz`), which achieved a final leaderboard score of **1211**. Later versions experiment with 2-player aggression, target breadth, fleet sizing, and defensive behavior.

This repo is an active competition workspace, so replay files, logs, and submission archives may represent the latest iteration rather than a final polished release.
