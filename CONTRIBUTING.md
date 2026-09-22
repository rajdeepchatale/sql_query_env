# Contributing

Issues and pull requests are welcome. This guide covers local setup, the test suite, and how to add a task.

## Setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/rajdeepchatale/sql_query_env.git
cd sql_query_env
uv sync --extra dev
```

## Run the server

```bash
uv run server                      # http://localhost:8000
curl http://localhost:8000/health
```

## Checks

CI runs the same three commands on every push and pull request:

```bash
uv run ruff check .
uv run pytest -q
uv run openenv validate .
```

The test suite checks:

- every reference query runs and is graded as correct
- the manifest, the task registry, and the baseline script list the same tasks
- the database rejects writes, `PRAGMA`, and `ATTACH`
- runaway queries are cut off
- known ways to game the reward stay closed

## Adding a task

1. If the task needs a new domain, add its schema, seed data, and schema description to `server/tasks.py` and register it in `SCHEMAS`.
2. Add a `Task` to the matching list in `server/tasks.py` with:
   - a `question` that states every filter the reference query applies. Hidden conditions make a task unfair, not harder.
   - `ground_truth_query` and `expected_columns`, which must match the query's output column names.
   - `difficulty`, `hints` (ordered from general to specific), and `max_steps`.
3. Add the task to `openenv.yaml`.
4. Add the task ID to `TASK_IDS` in `inference.py`.
5. Run `uv run pytest -q`. The consistency tests fail if you skipped step 3 or 4.

When the reference query sorts on a key that can tie, keep in mind that any tie order counts as correct. Row order is not part of the correctness check.

## Things to know

- **Import fallbacks.** The server runs in several layouts (`uv run server`, `uvicorn server.app:app`, `python -m sql_query_env.server.app`), and each one resolves imports differently. That's why several modules have `try`/`except ImportError` import blocks. Keep them.
- **SQLite threading.** Connections use `check_same_thread=False` because the server calls the environment from a thread pool. Each episode has its own in-memory database, so there is no shared state. Revisit this if you change the session model.
- **Read-only database.** `create_database()` installs an SQLite authorizer after seeding. If a new task needs a feature the authorizer blocks, allow the specific action code rather than removing the authorizer.
