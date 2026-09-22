"""
Core environment logic for the SQL query environment.

Each episode creates a fresh in-memory SQLite database for the chosen
domain, so no state leaks between episodes. The database is read-only once
seeded, and in-memory SQLite databases are cheap enough to build per episode.
"""

import random
import sqlite3
from typing import List, Optional
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
    from .graders import grade_query
    from .tasks import (
        ALL_TASKS_LIST,
        SCHEMAS,
        TASK_MAP,
        Task,
        create_database,
        get_expected_result,
    )
except ImportError:
    from server.graders import grade_query
    from server.tasks import (
        ALL_TASKS_LIST,
        SCHEMAS,
        TASK_MAP,
        Task,
        create_database,
        get_expected_result,
    )


class SqlQueryEnvironment(Environment):
    """Main environment class - presents schema + question, grades SQL.

    ``reset(task_id=...)`` selects a specific task; without one, tasks are
    served from a shuffled queue that cycles through all tasks (pass
    ``seed`` for a reproducible order). The episode ends when the query's
    result matches the reference exactly or the task's attempt budget runs
    out. Query history and best score are tracked across steps for the
    repeated-query penalty and progressive hints.
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._db: Optional[sqlite3.Connection] = None
        self._current_task: Optional[Task] = None
        self._current_schema_id: Optional[str] = None
        self._expected_row_count: int = 0
        self._previous_queries: List[str] = []
        self._best_score: float = 0.0
        self._step_rewards: List[float] = []
        self._rng = random.Random()
        self._task_queue: List[str] = []
        self._current_task_index: int = 0

    def _select_task(self, task_id: Optional[str] = None) -> Task:
        """Pick a specific task or grab the next one from the shuffled queue."""
        if task_id is not None:
            if task_id not in TASK_MAP:
                raise ValueError(
                    f"Unknown task_id {task_id!r}. Valid ids: {', '.join(sorted(TASK_MAP))}"
                )
            return TASK_MAP[task_id]

        # lazy-init the queue
        if not self._task_queue:
            self._task_queue = [t.id for t in ALL_TASKS_LIST]
            self._rng.shuffle(self._task_queue)
            self._current_task_index = 0

        if self._current_task_index >= len(self._task_queue):
            self._current_task_index = 0

        task = TASK_MAP[self._task_queue[self._current_task_index]]
        self._current_task_index += 1
        return task

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **kwargs,
    ) -> SqlQueryObservation:
        """Start a new episode.

        Args:
            seed: Reseeds the task queue so un-targeted resets are reproducible.
            episode_id: Optional custom episode identifier.
            task_id: Run a specific task (see ``openenv.yaml`` for ids).

        Creates a fresh DB for the task's domain and returns the initial
        observation with schema, question, and the first hint.
        """
        if seed is not None:
            self._rng.seed(seed)
            self._task_queue = []

        self._state = State(episode_id=episode_id or str(uuid4()), step_count=0)
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
        self._expected_row_count = len(
            get_expected_result(self._db, self._current_task.ground_truth_query)
        )

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
            expected_row_count=self._expected_row_count,
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

    def step(
        self,
        action: SqlQueryAction,
        timeout_s: Optional[float] = None,
        **kwargs,
    ) -> SqlQueryObservation:
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

        # done if the result is exactly right or out of attempts
        is_done = grade_result.is_correct or steps_remaining <= 0

        # build history for the observation
        history = [
            {
                "step": i + 1,
                "query": q[:100] + "..." if len(q) > 100 else q,
                "score": round(s, 2),
            }
            for i, (q, s) in enumerate(
                zip(self._previous_queries, self._step_rewards, strict=True)
            )
        ]

        feedback = grade_result.feedback

        # add hints if the agent is struggling
        if not is_done:
            hint_text = self._progressive_hints(step)
            if hint_text:
                feedback += f"\n\nHints (attempt {step}):\n{hint_text}"

        if is_done:
            if grade_result.is_correct:
                feedback += "\n\nCorrect: the result set matches the expected output."
            else:
                feedback += f"\n\nEpisode finished. Best score: {self._best_score:.2f}"
            feedback += f"\nScore progression: {' -> '.join(f'{s:.2f}' for s in self._step_rewards)}"

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
            expected_row_count=self._expected_row_count,
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
                "is_correct": grade_result.is_correct,
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
