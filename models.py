"""
Pydantic models for the SQL environment's action/observation space.

We tried keeping the observation minimal at first but realized the agent
needs way more context to actually improve between steps - so we added
diagnostics, efficiency notes, history etc. Bit of a chonky payload but
it's all text so doesn't matter much for perf.
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
    Full observation returned after each step.

    We pack a lot in here because the agent needs to understand what went
    wrong and how to fix it. The alternative was returning just a score,
    but that gives basically zero learning signal.
    """

    # task context
    task_id: str = Field(default="", description="Current task identifier")
    difficulty: str = Field(default="easy", description="easy, medium, or hard")
    database_domain: str = Field(
        default="company", description="Which database domain this task uses"
    )
    question: str = Field(default="", description="Natural language question to answer with SQL")
    schema_description: str = Field(
        default="", description="Full database schema with table definitions"
    )

    # query feedback
    query_result: str = Field(default="", description="Formatted result of the last query")
    query_error: Optional[str] = Field(default=None, description="SQL error message, if any")
    feedback: str = Field(default="", description="Detailed grading feedback")

    # structured diagnostics - these are the key differentiator
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
