# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Typed models for the pull request review environment."""

from typing import Any

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class MyAction(Action):
    """Agent submission for a pull request review round."""

    review_json: str = Field(
        ...,
        description=(
            "JSON string containing the review submission with keys such as "
            "`findings`, `overall_summary`, `confidence`, and `test_plan`."
        ),
    )


class MyObservation(Observation):
    """Observation returned to the agent during an episode."""

    task_id: str = Field(..., description="Unique task identifier.")
    title: str = Field(..., description="Human-readable task title.")
    difficulty: str = Field(..., description="Task difficulty: easy, medium, or hard.")
    scenario: str = Field(..., description="Business context for the pull request.")
    pull_request_summary: str = Field(..., description="Summary of the proposed code change.")
    diff_text: str = Field(..., description="Unified diff under review.")
    changed_files: list[str] = Field(
        default_factory=list,
        description="Files touched by the pull request.",
    )
    review_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Expected submission schema for the agent response.",
    )
    feedback: str = Field(
        default="",
        description="Feedback from the environment after a review attempt.",
    )
    reward: float = Field(..., description="Immediate reward delta for the latest step.")
    cumulative_reward: float = Field(
        ...,
        description="Best cumulative score achieved in the episode.",
    )
    done: bool = Field(default=False, description="Whether the episode is complete.")
    remaining_attempts: int = Field(
        default=0,
        description="How many attempts remain in the current episode.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra structured metadata, including score breakdowns.",
    )
