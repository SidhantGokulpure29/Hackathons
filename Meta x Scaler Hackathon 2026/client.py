# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Client for the pull request review environment."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

try:
    from .models import MyAction, MyObservation
except ImportError:
    from models import MyAction, MyObservation


class MyEnv(EnvClient[MyAction, MyObservation, State]):
    """Typed client for the submission environment."""

    def _step_payload(self, action: MyAction) -> Dict:
        """
        Convert MyAction to JSON payload for step message.

        Args:
            action: MyAction instance

        Returns:
            Dictionary representation suitable for JSON encoding
        """
        return {"review_json": action.review_json}

    def _parse_result(self, payload: Dict) -> StepResult[MyObservation]:
        """
        Parse server response into StepResult[MyObservation].

        Args:
            payload: JSON response data from server

        Returns:
            StepResult with MyObservation
        """
        obs_data = payload.get("observation", {})
        observation = MyObservation(
            task_id=obs_data.get("task_id", ""),
            title=obs_data.get("title", ""),
            difficulty=obs_data.get("difficulty", ""),
            scenario=obs_data.get("scenario", ""),
            pull_request_summary=obs_data.get("pull_request_summary", ""),
            diff_text=obs_data.get("diff_text", ""),
            changed_files=obs_data.get("changed_files", []),
            review_schema=obs_data.get("review_schema", {}),
            feedback=obs_data.get("feedback", ""),
            reward=payload.get("reward", obs_data.get("reward", 0.0)),
            cumulative_reward=obs_data.get("cumulative_reward", 0.0),
            done=payload.get("done", obs_data.get("done", False)),
            remaining_attempts=obs_data.get("remaining_attempts", 0),
            metadata=obs_data.get("metadata", {}),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward", observation.reward),
            done=payload.get("done", observation.done),
        )

    def _parse_state(self, payload: Dict) -> State:
        """
        Parse server response into State object.

        Args:
            payload: JSON response from state request

        Returns:
            State object with episode_id and step_count
        """
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
            done=payload.get("done", False),
        )
