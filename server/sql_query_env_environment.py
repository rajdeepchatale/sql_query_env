"""
Core environment logic for the SQL query environment.

Each episode creates a fresh in-memory SQLite database for the chosen
domain so there's no state leaking between episodes. SQLite in-memory
databases are cheap to spin up so this doesn't hurt performance.

TODO(team): might want to add a "curriculum mode" that auto-selects
tasks of increasing difficulty within a session. For now we just let
the caller pick or we cycle through randomly.
"""

import random
import sqlite3
from typing import Dict, List, Optional
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

# Handle both import paths — running via `uv run server` uses a different
# package layout than `python -m sql_query_env.server.app`
try:
    from ..models import SqlQueryAction, SqlQueryObservation
except ImportError:
    from models import SqlQueryAction, SqlQueryObservation

try:
    from .tasks import (
        ALL_TASKS,
        ALL_TASKS_LIST,
        SCHEMAS,
        TASK_MAP,
        Task,
        create_database,
        get_expected_result,
    )
    from .graders import grade_query, GradeResult
except ImportError:
    from server.tasks import (
        ALL_TASKS,
        ALL_TASKS_LIST,
        SCHEMAS,
        TASK_MAP,
        Task,
        create_database,
        get_expected_result,
    )
    from server.graders import grade_query, GradeResult


class SqlQueryEnvironment(Environment):
    """Main environment class - presents schema + question, grades SQL.

    Steps are independent in terms of DB state (no writes accumulate).
    We track query history and best score across steps for penalty logic
    and progressive hints.
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._db: Optional[sqlite3.Connection] = None
        self._current_task: Optional[Task] = None
        self._current_schema_id: Optional[str] = None
        self._previous_queries: List[str] = []
        self._best_score: float = 0.0
        self._step_rewards: List[float] = []
        self._task_queue: List[str] = []
        self._current_task_index: int = 0

    def _get_task_list(self) -> List[str]:
        """Shuffle task IDs for random ordering."""
        all_ids = [t.id for t in ALL_TASKS_LIST]
        random.shuffle(all_ids)
        return all_ids

    def _select_task(self, task_id: Optional[str] = None) -> Task:
        """Pick a specific task or grab the next one from the queue."""
        if task_id and task_id in TASK_MAP:
            return TASK_MAP[task_id]

        # lazy-init the queue
        if not self._task_queue:
            self._task_queue = self._get_task_list()
            self._current_task_index = 0

        if self._current_task_index >= len(self._task_queue):
            self._current_task_index = 0

        task = TASK_MAP[self._task_queue[self._current_task_index]]
        self._current_task_index += 1
        return task

    def reset(self, task_id: Optional[str] = None) -> SqlQueryObservation:
        """Start a new episode.

        Creates a fresh DB for the task's domain and returns the initial
        observation with schema, question, and hints.
        """
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._previous_queries = []
        self._best_score = 0.0
        self._step_rewards = []

        self._current_task = self._select_task(task_id)
        self._current_schema_id = self._current_task.schema_id

        # close old connection if any
        if self._db:
            try:
                self._db.close()
            except Exception:
                pass
        self._db = create_database(self._current_schema_id)

        schema = SCHEMAS[self._current_schema_id]
        expected_rows = get_expected_result(self._db, self._current_task.ground_truth_query)

        return SqlQueryObservation(
            task_id=self._current_task.id,
            difficulty=self._current_task.difficulty,
            database_domain=schema.name,
            question=self._current_task.question,
            schema_description=schema.description,
            query_result="",
            query_error=None,
            feedback=(
                f"Task: {self._current_task.description}\n"
                f"Database: {schema.name}\n"
                f"Difficulty: {self._current_task.difficulty}\n"
                f"Attempts available: {self._current_task.max_steps}\n"
                f"\nHints:\n" + "\n".join(f"  - {h}" for h in self._current_task.hints[:1])
            ),
            diagnostics=[],
            efficiency_notes=[],
            expected_row_count=len(expected_rows),
            expected_columns=self._current_task.expected_columns,
            steps_remaining=self._current_task.max_steps,
            current_score=0.0,
            history=[],
            done=False,
            reward=0.0,
        )

    def _progressive_hints(self, step: int) -> str:
        """Reveal more hints as the agent struggles.

        Step 1: just the first hint
        Step 2-3: a few more
        Step 4+: everything we've got
        """
        task = self._current_task
        hints = task.hints

        if step <= 1:
            shown = hints[:1] if hints else []
        elif step <= 3:
            shown = hints[:min(step + 1, len(hints))]
        else:
            shown = hints

        if not shown:
            return ""
        return "\n".join(f"  - {h}" for h in shown)

    def step(self, action: SqlQueryAction) -> SqlQueryObservation:
        """Evaluate a submitted SQL query and return graded feedback."""
        if self._current_task is None or self._db is None:
            return SqlQueryObservation(
                feedback="Environment not initialized. Call reset() first.",
                done=True,
                reward=0.0,
            )

        self._state.step_count += 1
        step = self._state.step_count
        steps_remaining = self._current_task.max_steps - step

        # grade it
        grade_result = grade_query(
            conn=self._db,
            query=action.query,
            task=self._current_task,
            previous_queries=self._previous_queries,
        )

        self._previous_queries.append(action.query)
        self._step_rewards.append(grade_result.total_score)
        self._best_score = max(self._best_score, grade_result.total_score)

        # done if near-perfect or out of steps
        is_done = grade_result.total_score >= 0.95 or steps_remaining <= 0

        # build history for the observation
        history = [
            {
                "step": i + 1,
                "query": q[:100] + "..." if len(q) > 100 else q,
                "score": round(s, 2),
            }
            for i, (q, s) in enumerate(
                zip(self._previous_queries, self._step_rewards)
            )
        ]

        feedback = grade_result.feedback

        # add hints if the agent is struggling
        if not is_done and grade_result.total_score < 0.95:
            hint_text = self._progressive_hints(step)
            if hint_text:
                feedback += f"\n\nHints (attempt {step}):\n{hint_text}"

        if is_done:
            if grade_result.total_score >= 0.95:
                feedback += "\n\nNear-perfect score achieved."
            else:
                feedback += f"\n\nEpisode finished. Best score: {self._best_score:.2f}"
            feedback += f"\nScore progression: {' -> '.join(f'{s:.2f}' for s in self._step_rewards)}"

        expected_rows = get_expected_result(self._db, self._current_task.ground_truth_query)
        schema = SCHEMAS[self._current_schema_id]

        return SqlQueryObservation(
            task_id=self._current_task.id,
            difficulty=self._current_task.difficulty,
            database_domain=schema.name,
            question=self._current_task.question,
            schema_description=schema.description,
            query_result=grade_result.query_result or "",
            query_error=grade_result.error,
            feedback=feedback,
            diagnostics=[d.to_dict() for d in grade_result.diagnostics],
            efficiency_notes=grade_result.efficiency_notes,
            expected_row_count=len(expected_rows),
            expected_columns=self._current_task.expected_columns,
            steps_remaining=max(0, steps_remaining),
            current_score=self._best_score,
            history=history,
            done=is_done,
            reward=grade_result.total_score,
            metadata={
                "task_id": self._current_task.id,
                "difficulty": self._current_task.difficulty,
                "database_domain": self._current_schema_id,
                "step": step,
                "best_score": self._best_score,
                "syntax_score": grade_result.syntax_score,
                "table_score": grade_result.table_score,
                "column_score": grade_result.column_score,
                "result_score": grade_result.result_score,
                "efficiency_score": grade_result.efficiency_score,
                "penalty": grade_result.penalty,
                "challenge_type": self._current_task.challenge_type,
            },
        )

    @property
    def state(self) -> State:
        return self._state

    def close(self):
        if self._db:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None
