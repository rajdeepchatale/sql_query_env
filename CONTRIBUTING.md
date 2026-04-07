# Development Notes

Quick reference for our team on how to work on this project.

## Setup

```bash
# clone and install
git clone <repo-url>
cd sql_query_env
uv sync
```

## Running locally

```bash
# start the server
uv run server

# test with curl
curl http://localhost:8000/health
```

## Adding a new task

1. Add the database seed data (if new domain) to `server/tasks.py`
2. Create a `Task` object with:
   - Ground truth SQL query
   - Expected output columns
   - Difficulty level and hints
3. Add task ID to the appropriate list in `tasks.py`
4. Add task entry in `openenv.yaml`
5. Add task ID to `TASK_IDS` in `inference.py` (for baseline testing)
6. Test: start server, call `/reset` with the new task ID, verify grading

## Testing grading

We have a quick sanity check you can run:

```python
import sqlite3
from server.tasks import create_database, TASK_MAP
from server.graders import grade_query

conn = create_database("company")
task = TASK_MAP["company_easy_1"]

# should score ~0.95+
result = grade_query(conn, task.ground_truth_query, task, [])
print(f"Ground truth score: {result.total_score}")

# should score ~0.10 (syntax only)
result = grade_query(conn, "SELECT 1", task, [])
print(f"Bad query score: {result.total_score}")
```

## Common issues

- **SQLite threading**: We use `check_same_thread=False` because FastAPI
  is async. The in-memory databases are per-episode so there's no real
  contention, but be aware of this if you change the session model.

- **Import errors**: The server can be run multiple ways (`uv run server`,
  `python -m sql_query_env.server.app`, `uvicorn server.app:app`) and
  each has a different package layout. That's why there are try/except
  import blocks. Don't remove them.
