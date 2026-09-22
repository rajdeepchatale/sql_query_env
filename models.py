"""
Pydantic models for the SQL environment's action/observation space.

The observation is deliberately rich: besides the score, it carries the
query result, structured diagnostics, style notes, and the attempt history,
so an agent has what it needs to improve its query between steps.
"""

from typing import Dict, List, Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class SqlQueryAction(Action):
    """Agent submits a SQL query string."""

    query: str = Field(
        ...,
        description="SQL query to execute against the database. Must be a valid SELECT statement.",
    )


class SqlQueryObservation(Observation):
    """
    Full observation returned by ``reset()`` and after each step.

    A bare score says that a query is wrong but not why; the diagnostics and
    feedback fields say what to change on the next attempt.
    """

    # task context
    task_id: str = Field(default="", description="Current task identifier")
    difficulty: str = Field(default="easy", description="easy, medium, or hard")
    database_domain: str = Field(
        default="", description="Which database domain this task uses"
    )
    question: str = Field(default="", description="Natural language question to answer with SQL")
    schema_description: str = Field(
        default="", description="Full database schema with table definitions"
    )

    # query feedback
    query_result: str = Field(default="", description="Formatted result of the last query")
    query_error: Optional[str] = Field(default=None, description="SQL error message, if any")
    feedback: str = Field(default="", description="Detailed grading feedback")

    # structured, machine-readable feedback for process supervision
    diagnostics: List[Dict] = Field(
        default_factory=list,
        description="Structured error diagnostics: type, severity, message, suggestion",
    )
    efficiency_notes: List[str] = Field(
        default_factory=list,
        description="SQL best-practice tips based on the submitted query",
    )

    # hints to help the agent
    expected_row_count: int = Field(default=0, description="Expected number of result rows")
    expected_columns: List[str] = Field(default_factory=list, description="Expected column names")

    # episode progress
    steps_remaining: int = Field(default=0, description="Attempts left in this episode")
    current_score: float = Field(default=0.0, description="Best score so far (0.0-1.0)")
    history: List[Dict] = Field(default_factory=list, description="Previous queries and scores")
