"""Local validation script for the Round 1 submission."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from my_env.server.my_env_environment import MyEnvironment
    from my_env.review_tasks import REVIEW_TASKS
except ModuleNotFoundError:
    from review_tasks import REVIEW_TASKS
    from server.my_env_environment import MyEnvironment


def validate_tasks() -> None:
    assert len(REVIEW_TASKS) >= 3, "Need at least 3 tasks."
    difficulties = {task["difficulty"] for task in REVIEW_TASKS}
    assert {"easy", "medium", "hard"}.issubset(difficulties), "Need easy, medium, and hard tasks."


def build_gold_review(task: dict) -> dict:
    findings = []
    for issue in task["expected_findings"]:
        findings.append(
            {
                "file": issue["file"],
                "severity": issue["severity"],
                "category": issue["category"],
                "title": issue["match_keywords"][0].title(),
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


def validate_environment_logic() -> None:
    sequential_env = MyEnvironment()
    observed_ids = [sequential_env.reset().task_id for _ in range(len(REVIEW_TASKS))]
    expected_ids = [task["id"] for task in REVIEW_TASKS]
    assert observed_ids == expected_ids, "Default reset order should cover all tasks deterministically."

    for task in REVIEW_TASKS:
        env = MyEnvironment(force_task_id=task["id"])
        reset_obs = env.reset()
        assert reset_obs.task_id == task["id"]
        assert reset_obs.done is False
        assert "expected_findings" not in reset_obs.metadata

        action = type("ActionLike", (), {"review_json": json.dumps(build_gold_review(task))})()
        result_obs = env.step(action)
        assert 0.0 < result_obs.reward <= 1.0, f"reward {result_obs.reward} not in (0,1]"
        assert 0.0 < result_obs.cumulative_reward < 1.0, f"cumulative_reward {result_obs.cumulative_reward} not in (0,1)"


def validate_http(base_url: str) -> None:
    for path in ["/health", "/docs"]:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}{path}", timeout=10) as response:
            assert response.status == 200, f"Expected 200 for {path}, got {response.status}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()

    validate_tasks()
    validate_environment_logic()
    print("PASS task count and local grading checks")

    if args.base_url:
        try:
            validate_http(args.base_url)
            print("PASS HTTP health/docs checks")
        except urllib.error.URLError as exc:
            raise SystemExit(f"HTTP validation failed: {exc}") from exc

    print("Submission validation completed successfully")


if __name__ == "__main__":
    main()
