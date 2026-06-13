"""Tests for the pull request review environment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from my_env.review_tasks import REVIEW_TASKS
    from my_env.server.my_env_environment import MyEnvironment
except ModuleNotFoundError:
    from review_tasks import REVIEW_TASKS
    from server.my_env_environment import MyEnvironment


def make_review(task: dict, quality: str = "strong") -> dict:
    if quality == "weak":
        return {
            "findings": [
                {
                    "file": task["changed_files"][0],
                    "severity": "low",
                    "category": "style",
                    "title": "Maybe clean this up",
                    "explanation": "Could be simplified.",
                    "suggested_fix": "Refactor later.",
                }
            ],
            "overall_summary": "Looks mostly okay.",
            "confidence": 0.2,
            "test_plan": ["Run unit tests."],
        }

    findings = []
    for issue in task["expected_findings"]:
        findings.append(
            {
                "file": issue["file"],
                "severity": issue["severity"],
                "category": issue["category"],
                "title": issue["match_keywords"][0],
                "explanation": " ".join(issue["explanation_keywords"]),
                "suggested_fix": " ".join(issue["suggested_fix_keywords"]),
            }
        )
    return {
        "findings": findings,
        "overall_summary": " ".join(task["summary_keywords"]),
        "confidence": 0.9,
        "test_plan": task["test_keywords"],
    }


def test_reset_hides_gold_labels() -> None:
    env = MyEnvironment(force_task_id=REVIEW_TASKS[0]["id"])
    observation = env.reset()

    assert observation.task_id == REVIEW_TASKS[0]["id"]
    assert "correct_comment" not in observation.model_dump_json()
    assert observation.remaining_attempts == 2


def test_default_reset_cycles_through_all_tasks_in_order() -> None:
    env = MyEnvironment()
    observed_ids = [env.reset().task_id for _ in range(len(REVIEW_TASKS))]

    assert observed_ids == [task["id"] for task in REVIEW_TASKS]


def test_strong_review_scores_higher_than_weak_review() -> None:
    task = REVIEW_TASKS[1]

    weak_env = MyEnvironment(force_task_id=task["id"])
    weak_env.reset()
    weak_obs = weak_env.step(type("ActionLike", (), {"review_json": json.dumps(make_review(task, "weak"))})())

    strong_env = MyEnvironment(force_task_id=task["id"])
    strong_env.reset()
    strong_obs = strong_env.step(type("ActionLike", (), {"review_json": json.dumps(make_review(task, "strong"))})())

    assert strong_obs.cumulative_reward > weak_obs.cumulative_reward
    assert 0.0 <= strong_obs.cumulative_reward <= 1.0


def test_invalid_json_gives_feedback_without_crashing() -> None:
    env = MyEnvironment(force_task_id=REVIEW_TASKS[2]["id"])
    env.reset()
    observation = env.step(type("ActionLike", (), {"review_json": "{not-json"})())

    assert observation.reward == 0.0
    assert "valid JSON" in observation.feedback
    assert observation.metadata["invalid_submission_penalty"] == 0.0
