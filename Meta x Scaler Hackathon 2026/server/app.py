# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""FastAPI app for the pull request review environment."""

from fastapi import HTTPException

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:  # pragma: no cover
    raise ImportError(
        "openenv is required for the web interface. Install dependencies with '\n    uv sync\n'"
    ) from e

try:
    from ..models import MyAction, MyObservation
    from .my_env_environment import MyEnvironment
    from ..review_tasks import REVIEW_TASKS, build_reference_review
except ImportError:
    from models import MyAction, MyObservation
    from server.my_env_environment import MyEnvironment
    from review_tasks import REVIEW_TASKS, build_reference_review


app = create_app(
    MyEnvironment,
    MyAction,
    MyObservation,
    env_name="my_env",
    max_concurrent_envs=4,
)


@app.get("/tasks")
def list_tasks():
    """Expose task/grader metadata for validator discovery."""

    return {
        "tasks": [
            {
                "task_id": task["id"],
                "title": task["title"],
                "difficulty": task["difficulty"],
                "has_grader": True,
                "grader_name": "deterministic_pr_review_grader",
                "grader_type": "deterministic",
            }
            for task in REVIEW_TASKS
        ]
    }


@app.get("/grade/{task_id}")
def grade_task(task_id: str):
    """Return a deterministic in-range score for a known task."""

    task = next((task for task in REVIEW_TASKS if task["id"] == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Unknown task_id: {task_id}")

    env = MyEnvironment(force_task_id=task_id)
    env.reset()
    score, _, _ = env._grade_submission(build_reference_review(task))
    clamped = float(min(0.95, max(0.05, score)))
    return {
        "task_id": task_id,
        "score": clamped,
        "has_grader": True,
        "grader_name": "deterministic_pr_review_grader",
    }


@app.get("/validate")
def validate_tasks():
    """Convenience validator endpoint for task/grader checks."""

    task_scores = []
    for task in REVIEW_TASKS:
        env = MyEnvironment(force_task_id=task["id"])
        env.reset()
        score, _, _ = env._grade_submission(build_reference_review(task))
        clamped = float(min(0.95, max(0.05, score)))
        task_scores.append({
            "task_id": task["id"],
            "score": clamped,
            "has_grader": True,
            "grader_name": "deterministic_pr_review_grader",
        })
    return {
        "num_tasks": len(task_scores),
        "task_scores": task_scores,
        "all_scores_strictly_between_zero_and_one": all(0.0 < item["score"] < 1.0 for item in task_scores),
    }


def main(host: str = "0.0.0.0", port: int = 8000):
    """Run the app locally."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.port == 8000:
        main()
    else:
        main(port=args.port)
