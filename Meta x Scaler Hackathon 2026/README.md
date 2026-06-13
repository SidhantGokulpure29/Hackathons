---
title: PR Review Simulator Environment
emoji: 🧪
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
app_port: 8000
base_path: /web
tags:
  - openenv
  - code-review
  - rl
---

# PR Review Simulator

`my_env` is a real-world OpenEnv environment where an agent reviews pull requests, identifies defects, calibrates severity, and proposes targeted tests. It is designed for the Meta PyTorch OpenEnv Hackathon Round 1 rubric.

## Environment Overview

The environment simulates production pull requests across security, billing, privacy, and authorization workflows. Each episode gives the agent:

- business context
- a pull request summary
- a realistic unified diff
- the required JSON response schema

The agent submits a structured review. The environment then grades:

- issue detection quality
- file-level precision
- severity calibration
- summary quality
- test-plan quality
- false positives

The default reset order cycles deterministically through all three benchmark tasks, which makes baseline evaluation reproducible.

The agent gets up to **2 attempts** per task, and reward is the **improvement in best score** across attempts. This gives partial progress signals while keeping the task evaluator-friendly.

## Key Requirements Covered

This submission is built to satisfy the dashboard requirements:

- real-world task, not a toy or game
- full OpenEnv spec with typed models, `step()`, `reset()`, `state()`, and `openenv.yaml`
- minimum 3 tasks with easy, medium, and hard difficulty
- meaningful reward with partial progress signals
- baseline `inference.py` with reproducible behavior across all 3 tasks
- deployable to Hugging Face Spaces with a working Dockerfile
- README describing environment behavior, action/observation spaces, setup, checks, and deployment

## Task Set

- `easy-auth-token-leak`
  Authentication helper refactor that introduces unsafe token comparison and secret leakage in logs.
- `medium-billing-idempotency`
  Billing retry change that can create duplicate charges and mishandle webhook states.
- `hard-export-authorization`
  Support export endpoint that drops authorization checks and exposes PII plus session credentials.

## Action Space

`MyAction`

- `review_json`
  JSON string containing:
  - `findings`
  - `overall_summary`
  - `confidence`
  - `test_plan`

Each finding should include:

- `file`
- `severity`
- `category`
- `title`
- `explanation`
- `suggested_fix`

## Observation Space

`MyObservation`

- `task_id`
- `title`
- `difficulty`
- `scenario`
- `pull_request_summary`
- `diff_text`
- `changed_files`
- `review_schema`
- `feedback`
- `reward`
- `cumulative_reward`
- `done`
- `remaining_attempts`
- `metadata`

## Functional Requirements Mapping

- Real-world task simulation: satisfied via production-style pull request review workflows.
- OpenEnv compliance: typed `Action` and `Observation` models, plus `step()`, `reset()`, `state()`, and `openenv.yaml`.
- Minimum 3 tasks with deterministic graders: implemented in `review_tasks.py` with easy, medium, and hard tasks.
- Meaningful reward function: partial credit is awarded for issue detection, severity, summaries, and tests. False positives reduce score.
- Baseline inference script: uses the OpenAI client when `OPENAI_API_KEY` is available and otherwise falls back to a deterministic heuristic baseline. It evaluates all 3 tasks and reports an average score.

## Reward Logic

The total score is in `[0.0, 1.0]` and is based on:

- matching expected high-value findings
- correctness of file targeting
- severity accuracy
- impact explanation quality
- usefulness of proposed tests
- summary coverage
- penalty for false positives

Per-step reward is:

```text
max(0, current_total_score - previous_best_score)
```

Malformed submissions receive zero reward for that step, and low-quality extra findings are penalized through the false-positive term.

## Detailed Requirements

This repository is set up to match the detailed hackathon guidance:

- typed models are defined in `models.py`
- `step()`, `reset()`, and `state()` are implemented in `server/my_env_environment.py`
- `openenv.yaml` is present at the environment root
- at least 3 tasks exist with easy, medium, and hard difficulty
- a grader computes scores between `0.0` and `1.0`
- a Dockerfile is present for deployment
- `inference.py` lives in the environment root
- `validate_submission.py` gives you a local pre-submit check

## Evaluation Criteria

This repo is aligned to the dashboard criteria:

- runtime correctness: the environment runs and responds without errors
- interface compliance: typed models plus OpenEnv `step()/reset()/state()`
- task design: realistic, testable PR review scenarios
- grading logic: reward makes sense and captures partial correctness

## How Judging Works

Based on the dashboard, judging combines:

- programmatic checks
- rubric-based quality scoring

For this repo, the practical equivalents are:

- the environment deploys and responds over OpenEnv
- the Docker image builds
- `inference.py` runs successfully
- there are at least 3 graded tasks
- rewards stay in the valid range
- the review grader can distinguish strong, partial, and weak answers

## Pre-Submission Checklist

All of these should pass before final submission:

- HF Space deploys successfully
- `reset()` works on the deployed Space
- `openenv.yaml` is valid
- typed models are present
- `step()`, `reset()`, `state()` are working
- Dockerfile builds successfully
- `inference.py` runs from the project root
- `inference.py` produces structured `[START]`, `[STEP]`, `[END]` logs
- `inference.py` covers all 3 benchmark tasks and reports an aggregate score
- there are at least 3 tasks with graders
- each task scores in the `0.0` to `1.0` range
- runtime stays under 20 minutes
- the environment runs within roughly `2 vCPU / 8 GB RAM`

## Hackathon-Specific Notes

The dashboard requires:

- env vars: `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN`
- `inference.py` in the project root
- OpenAI Client for LLM calls
- structured stdout logs

This repo also supports `OPENAI_API_KEY` so the baseline can run against the standard OpenAI client flow.

## Setup

```bash
cd my_env
uv sync --extra dev
```

If you prefer `pip`:

```bash
cd my_env
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
pip install openai
```

## Local Run

Start the server:

```bash
cd my_env
.\.venv\Scripts\python.exe -m uvicorn my_env.server.app:app --app-dir .. --host 127.0.0.1 --port 8000
```

In another terminal, run the baseline inference:

```bash
cd my_env
.\.venv\Scripts\python.exe inference.py --base-url http://127.0.0.1:8000
```

If `OPENAI_API_KEY` or `HF_TOKEN` is not set, the script falls back to a deterministic heuristic baseline so you can still test locally without external API access.

## Checks And Tests

Run unit tests:

```bash
cd my_env
.\.venv\Scripts\python.exe -m pytest -q
```

Run the local validation script:

```bash
cd my_env
.\.venv\Scripts\python.exe validate_submission.py
```

Optional HTTP validation against a running server:

```bash
cd my_env
.\.venv\Scripts\python.exe validate_submission.py --base-url http://localhost:8000
```

If you have `openenv validate` available in your environment, run it as an additional compliance check from `my_env/` before submitting.

Build the Docker image:

```bash
cd my_env
docker build -t my_env-env:latest -f server/Dockerfile .
```

## Inference Script Contents

`inference.py`:

- reads `OPENAI_API_KEY` or `HF_TOKEN`
- optionally reads `API_BASE_URL`
- reads `MODEL_NAME`
- connects to the environment
- logs `[START]`
- evaluates all 3 benchmark tasks in deterministic order
- generates a structured review with either OpenAI Client or a deterministic heuristic fallback
- submits one or two review attempts per task
- logs `[STEP]` for each step
- logs `[END]` with per-task scores and the average score

## Deployment

Login to Hugging Face first:

```bash
hf auth login
```

Then deploy:

```bash
cd my_env
openenv push --repo-id <your-hf-username>/<your-space-name>
```

After the Space is created, set these Space variables:

- `API_BASE_URL`
- `MODEL_NAME`
- `HF_TOKEN`

Useful endpoints after deploy:

- `/health`
- `/docs`
- `/web`

## How To Submit

When your environment is live:

1. Open the Round 1 submission form on the dashboard.
2. Paste the Hugging Face Space URL.
3. Make sure the team lead performs the final submission if you are in a team.
4. Re-run `python validate_submission.py --base-url <space-url>` before the final click if you want one last sanity check.

## Recommended Final Workflow

```bash
cd my_env
uv sync --extra dev
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe validate_submission.py
.\.venv\Scripts\python.exe -m uvicorn my_env.server.app:app --app-dir .. --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe inference.py --base-url http://127.0.0.1:8000
docker build -t my_env-env:latest -f server/Dockerfile .
openenv push --repo-id <your-hf-username>/<your-space-name>
.\.venv\Scripts\python.exe validate_submission.py --base-url https://<your-space>.hf.space
```
