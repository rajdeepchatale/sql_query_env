"""Client for connecting to the SQL Query environment server."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from .models import SqlQueryAction, SqlQueryObservation


class SqlQueryEnv(
    EnvClient[SqlQueryAction, SqlQueryObservation, State]
):
    """
    WebSocket client for the SQL Query environment.

    Example usage::

        async with SqlQueryEnv(base_url="http://localhost:8000") as client:
            result = await client.reset()
            result = await client.step(SqlQueryAction(query="SELECT ..."))
    """

    def _step_payload(self, action: SqlQueryAction) -> Dict:
        return {"query": action.query}

    def _parse_result(self, payload: Dict) -> StepResult[SqlQueryObservation]:
        obs_data = payload.get("observation", {})
        observation = SqlQueryObservation(
            task_id=obs_data.get("task_id", ""),
            difficulty=obs_data.get("difficulty", "easy"),
            database_domain=obs_data.get("database_domain", ""),
            question=obs_data.get("question", ""),
            schema_description=obs_data.get("schema_description", ""),
            query_result=obs_data.get("query_result", ""),
            query_error=obs_data.get("query_error"),
            feedback=obs_data.get("feedback", ""),
            diagnostics=obs_data.get("diagnostics", []),
            efficiency_notes=obs_data.get("efficiency_notes", []),
            expected_row_count=obs_data.get("expected_row_count", 0),
            expected_columns=obs_data.get("expected_columns", []),
            steps_remaining=obs_data.get("steps_remaining", 0),
            current_score=obs_data.get("current_score", 0.0),
            history=obs_data.get("history", []),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
