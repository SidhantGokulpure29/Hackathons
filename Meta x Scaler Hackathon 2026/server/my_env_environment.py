# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Pull request review simulation environment."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import MyAction, MyObservation
    from ..review_tasks import REVIEW_TASKS, public_task_view
except ImportError:
    from models import MyAction, MyObservation
    from review_tasks import REVIEW_TASKS, public_task_view


MAX_ATTEMPTS = 2
MIN_SCORE = 0.05
MAX_SCORE = 0.95
GRADER_NAME = "deterministic_pr_review_grader"


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())


def _strict_score(value: float) -> float:
    """Clamp scores to the open interval (0, 1)."""

    return float(round(min(MAX_SCORE, max(MIN_SCORE, float(value))), 4))


class MyEnvironment(Environment):
    """Environment for reviewing realistic pull requests."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self, force_task_id: str | None = None):
        self._state = State(episode_id=str(uuid4()), step_count=0, done=False)
        self.force_task_id = force_task_id
        self.current_task: dict[str, Any] | None = None
        self.best_score = 0.0
        self._task_cursor = 0

    def _pick_task(self) -> dict[str, Any]:
        if self.force_task_id:
            for task in REVIEW_TASKS:
                if task["id"] == self.force_task_id:
                    return task
            raise ValueError(f"Unknown task id: {self.force_task_id}")
        task = REVIEW_TASKS[self._task_cursor % len(REVIEW_TASKS)]
        self._task_cursor += 1
        return task

    def reset(self) -> MyObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0, done=False)
        self.current_task = self._pick_task()
        self.best_score = MIN_SCORE
        public = public_task_view(self.current_task)
        return MyObservation(
            **public,
            feedback=(
                "Review the pull request and submit JSON matching `review_schema`. "
                "You have up to 2 attempts. Strong submissions identify concrete issues, "
                "calibrate severity, explain impact, and propose tests."
            ),
            reward=MIN_SCORE,
            cumulative_reward=MIN_SCORE,
            done=False,
            remaining_attempts=MAX_ATTEMPTS,
            metadata={"step": 0, "grader_name": GRADER_NAME, "has_grader": True},
        )

    def step(self, action: MyAction) -> MyObservation:  # type: ignore[override]
        if self.current_task is None:
            raise RuntimeError("Call reset() before step().")

        self._state.step_count += 1
        parsed_review, parse_feedback = self._parse_review_json(action.review_json)
        if parsed_review is None:
            done = self._state.step_count >= MAX_ATTEMPTS
            self._state.done = done
            public = public_task_view(self.current_task)
            return MyObservation(
                **public,
                feedback=parse_feedback,
                reward=MIN_SCORE,
                cumulative_reward=_strict_score(self.best_score),
                done=done,
                remaining_attempts=max(0, MAX_ATTEMPTS - self._state.step_count),
                metadata={
                    "step": self._state.step_count,
                    "valid_json": False,
                    "task_score": _strict_score(self.best_score),
                    "grader_name": GRADER_NAME,
                    "has_grader": True,
                },
            )

        total_score, breakdown, feedback = self._grade_submission(parsed_review)
        reward_delta = float(_strict_score(max(total_score - self.best_score, MIN_SCORE)))
        self.best_score = _strict_score(max(self.best_score, total_score))

        done = self.best_score >= 0.85 or self._state.step_count >= MAX_ATTEMPTS
        self._state.done = done
        public = public_task_view(self.current_task)
        return MyObservation(
            **public,
            feedback=feedback,
            reward=reward_delta,
            cumulative_reward=_strict_score(self.best_score),
            done=done,
            remaining_attempts=max(0, MAX_ATTEMPTS - self._state.step_count),
            metadata={
                "step": self._state.step_count,
                "valid_json": True,
                "task_score": _strict_score(self.best_score),
                "grader_name": GRADER_NAME,
                "has_grader": True,
            },
        )

    def _parse_review_json(self, raw_text: str) -> tuple[dict[str, Any] | None, str]:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return None, (
                "Submission must be valid JSON. "
                f"Parser error at line {exc.lineno}, column {exc.colno}. "
                "Return an object with `findings`, `overall_summary`, `confidence`, and `test_plan`."
            )

        required = {"findings", "overall_summary", "confidence", "test_plan"}
        missing = [key for key in required if key not in parsed]
        if missing:
            return None, f"Missing required keys: {', '.join(sorted(missing))}."
        if not isinstance(parsed["findings"], list):
            return None, "`findings` must be a list."
        if not isinstance(parsed["test_plan"], list):
            return None, "`test_plan` must be a list."
        return parsed, ""

    def _match_expected_issue(
        self,
        expected: dict[str, Any],
        candidate: dict[str, Any],
    ) -> float:
        file_score = 1.0 if _normalize_text(candidate.get("file", "")) == _normalize_text(expected["file"]) else 0.0

        combined_text = " ".join(
            [
                candidate.get("title", ""),
                candidate.get("category", ""),
                candidate.get("explanation", ""),
                candidate.get("suggested_fix", ""),
            ]
        )
        combined_text = _normalize_text(combined_text)

        keyword_hits = sum(1 for keyword in expected["match_keywords"] if _normalize_text(keyword) in combined_text)
        keyword_score = min(1.0, keyword_hits / max(1, len(expected["match_keywords"]) // 2))

        explanation_hits = sum(
            1 for keyword in expected["explanation_keywords"] if _normalize_text(keyword) in combined_text
        )
        explanation_score = min(1.0, explanation_hits / max(1, len(expected["explanation_keywords"]) // 2))

        fix_text = _normalize_text(candidate.get("suggested_fix", ""))
        fix_hits = sum(1 for keyword in expected["suggested_fix_keywords"] if _normalize_text(keyword) in fix_text)
        fix_score = min(1.0, fix_hits / max(1, len(expected["suggested_fix_keywords"])))

        severity_score = 1.0 if _normalize_text(candidate.get("severity", "")) == _normalize_text(expected["severity"]) else 0.0

        return _strict_score(
            0.30 * float(file_score)
            + 0.30 * keyword_score
            + 0.20 * explanation_score
            + 0.10 * fix_score
            + 0.10 * severity_score,
        )

    def _grade_submission(self, review: dict[str, Any]) -> tuple[float, dict[str, float], str]:
        assert self.current_task is not None

        findings = [item for item in review.get("findings", []) if isinstance(item, dict)]
        expected_issues = self.current_task["expected_findings"]

        matched_scores: list[float] = []
        matched_count = 0
        unmatched_candidates: set[int] = set(range(len(findings)))

        for expected in expected_issues:
            best_index = None
            best_score = 0.0
            for index in list(unmatched_candidates):
                score = self._match_expected_issue(expected, findings[index])
                if score > best_score:
                    best_index = index
                    best_score = score
            if best_index is not None and best_score >= 0.55:
                matched_count += 1
                matched_scores.append(best_score)
                unmatched_candidates.discard(best_index)
            else:
                matched_scores.append(0.0)

        issue_score = float(_strict_score(sum(matched_scores) / len(expected_issues)))

        summary_text = _normalize_text(str(review.get("overall_summary", "")))
        summary_hits = sum(
            1 for keyword in self.current_task["summary_keywords"] if _normalize_text(keyword) in summary_text
        )
        summary_score = float(_strict_score(
            min(1.0, summary_hits / max(1, len(self.current_task["summary_keywords"]) - 1))
        ))

        tests_text = _normalize_text(" ".join(str(item) for item in review.get("test_plan", [])))
        test_hits = sum(1 for keyword in self.current_task["test_keywords"] if _normalize_text(keyword) in tests_text)
        test_score = float(_strict_score(
            min(1.0, test_hits / max(1, len(self.current_task["test_keywords"]) - 1))
        ))

        confidence = review.get("confidence", 0)
        confidence_score = (
            _strict_score(1.0)
            if isinstance(confidence, (int, float)) and 0 <= confidence <= 1
            else MIN_SCORE
        )

        false_positive_penalty = min(0.25, 0.08 * len(unmatched_candidates))

        raw_total_score = (
            0.60 * issue_score
            + 0.15 * summary_score
            + 0.15 * test_score
            + 0.10 * confidence_score
            - false_positive_penalty
        )
        total_score = float(_strict_score(raw_total_score))

        breakdown = {"task_score": total_score, "grader_name": GRADER_NAME, "has_grader": True}

        missed = len(expected_issues) - matched_count
        feedback_parts = [
            f"Matched {matched_count}/{len(expected_issues)} high-value findings.",
            f"Summary coverage score: {summary_score:.2f}.",
            f"Test-plan score: {test_score:.2f}.",
        ]
        if missed:
            feedback_parts.append(
                "You still missed at least one important issue or did not explain it concretely enough."
            )
        if unmatched_candidates:
            feedback_parts.append(
                "Some findings look like false positives or are too vague to grade confidently."
            )
        if total_score >= 0.85:
            feedback_parts.append("Strong review. This is submission-quality.")
        else:
            feedback_parts.append(
                "Improve file-level precision, impact explanation, and concrete regression tests."
            )

        return total_score, breakdown, " ".join(feedback_parts)

    @property
    def state(self) -> State:
        return self._state
