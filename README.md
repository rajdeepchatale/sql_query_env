<h1 align="center">SQL Query</h1>

<p align="center">
  A text-to-SQL reinforcement-learning environment for <a href="https://github.com/meta-pytorch/OpenEnv">OpenEnv</a>,<br>
  with execution-based rewards and step-by-step diagnostic feedback.
</p>

<p align="center">
  <a href="https://github.com/rajdeepchatale/sql_query_env/actions/workflows/ci.yml"><img src="https://github.com/rajdeepchatale/sql_query_env/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-BSD--3--Clause-blue.svg" alt="License: BSD-3-Clause"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <a href="https://huggingface.co/spaces/rajdeepchatale/sql_query_env"><img src="https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Space-yellow.svg" alt="Hugging Face Space"></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#example-episode">Example</a> ·
  <a href="#tasks">Tasks</a> ·
  <a href="#reward">Reward</a> ·
  <a href="https://huggingface.co/spaces/rajdeepchatale/sql_query_env">Live Space</a>
</p>

---

## Overview

**SQL Query** trains and evaluates agents that turn natural-language questions into SQL. In each episode the agent receives a database schema and a question, then submits SQLite queries. Every query is executed against a sandboxed database and compared with a reference result. The agent gets a partial-credit reward and structured feedback on what to fix before its next attempt.

The environment was built for the Meta PyTorch OpenEnv Hackathon 2026.

## Highlights

- **Verifiable, deterministic grading.** Queries are executed and their rows compared with a reference result, with no LLM judge involved.
- **Dense reward signal.** Five scoring components give credit for partial progress, such as correct tables with a wrong aggregate.
- **Actionable feedback.** Typed diagnostics (`MISSING_JOIN`, `NULL_HANDLING`, `EXTRA_ROWS`, …) and progressive hints support correction within an episode.
- **Generalization across schemas.** 14 tasks over three domains, ranging from single-table filters to self-joins, anti-joins, and division-by-zero edge cases.
- **Safe execution.** Read-only databases, per-query time and row limits, and a fresh database for every episode.

## How it works

1. `reset()` selects a task, either at random or with `reset(task_id=...)`, and builds an in-memory SQLite database for its domain.
2. The observation contains the schema, the question, the expected output columns and row count, and a first hint.
3. The agent submits `SqlQueryAction(query="SELECT ...")`.
4. The grader executes the query, compares the result with the reference, and returns a reward in `[0, 1]` with feedback and diagnostics.
5. The episode ends when the result matches exactly or the attempt budget (5–10 per task) runs out.

## Example episode

Task `company_medium_2`, output from the environment:

```text
Question   Considering only active employees, find the average salary per department,
           but only show departments where that average exceeds $100,000. ...
Expected   columns: name, avg_salary · rows: 3

Attempt 1  SELECT d.name, AVG(e.salary) AS avg_salary
           FROM employees e JOIN departments d ON e.department_id = d.id
           GROUP BY d.name HAVING AVG(e.salary) > 100000
           ORDER BY avg_salary DESC

Reward     0.82  (syntax 0.10 + tables 0.15 + columns 0.20 + results 0.30 + efficiency 0.07)
Diagnostic MISSING_ROWS: Got 2 rows but expected 3.

Attempt 2  ... same query with WHERE e.is_active = 1 before GROUP BY ...

Reward     0.97  Correct: the result set matches the expected output. Episode done.
```

## Quickstart

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/rajdeepchatale/sql_query_env.git
cd sql_query_env
uv sync
uv run server            # serves on http://localhost:8000
```

Connect from Python:

```python
import asyncio
from sql_query_env import SqlQueryAction, SqlQueryEnv

async def main():
    async with SqlQueryEnv(base_url="http://localhost:8000") as env:
        result = await env.reset(task_id="company_easy_1")
        print(result.observation.question)

        result = await env.step(SqlQueryAction(
            query="SELECT name, salary FROM employees ORDER BY salary DESC"
        ))
        print(result.reward, result.done)
        for diag in result.observation.diagnostics:
            print(f"[{diag['type']}] {diag['message']}")

asyncio.run(main())
```

Or run it in Docker:

```bash
docker build -t sql_query_env .
docker run -p 8000:8000 sql_query_env
```

## Tasks

Three database domains, each with its own schema:

| Domain | Tables |
|---|---|
| Company Analytics | departments, employees, products, customers, orders, reviews |
| Hospital Management | wards, doctors, patients, appointments, medications, prescriptions |
| E-Commerce Platform | sellers, categories, products, users, orders, order_items, returns |

| Task ID | Difficulty | Task | Tests | Attempts |
|---|---|---|---|---|
| `company_easy_1` | Easy | Active Engineering employees by salary | Filter + JOIN + sort | 5 |
| `company_easy_2` | Easy | Electronics products over $50 | Single-table filter | 5 |
| `hospital_easy_1` | Easy | Patients still admitted | `IS NULL` | 5 |
| `ecommerce_easy_1` | Easy | Premium users by signup date | Boolean flag filter | 5 |
| `company_medium_1` | Medium | Revenue per category, completed orders | JOIN + GROUP BY | 6 |
| `company_medium_2` | Medium | Departments averaging > $100K (active staff) | GROUP BY + HAVING | 6 |
| `hospital_medium_1` | Medium | Active medication cost per admitted patient | 3-table JOIN + two NULL filters | 7 |
| `ecommerce_medium_1` | Medium | Revenue per seller, delivered orders | 4-table JOIN chain | 7 |
| `company_hard_1` | Hard | Salary-to-budget utilization per department | Computed percentage | 8 |
| `company_hard_2` | Hard | Employees earning more than their manager | Self-join | 8 |
| `hospital_hard_1` | Hard | Prescriptions to patients outside the doctor's ward | Same table joined twice | 10 |
| `hospital_hard_2` | Hard | Repeat visits to the same doctor | Pairwise GROUP BY + MIN/MAX | 8 |
| `ecommerce_hard_1` | Hard | Return rate per category | Subquery + LEFT JOIN + COALESCE | 10 |
| `ecommerce_hard_2` | Hard | In-stock products never ordered | Anti-join | 8 |

## Reward

| Component | Weight | Measures |
|---|---|---|
| Syntax | 0.10 | The query executes |
| Tables | 0.15 | Share of the reference query's tables that are referenced |
| Columns | 0.20 | Share of expected output columns present |
| Results | 0.45 | How closely the returned rows match the reference rows |
| Efficiency | 0.10 | SQL style: aliases, explicit columns, no needless `DISTINCT` or comma joins |

**Penalties:** −0.10 for destructive SQL, which is also rejected without being executed, and −0.05 for resubmitting an identical query. The total is clamped to `[0, 1]`.

**Result comparison**

- Rows are compared as a multiset, so duplicates from a join fan-out count against the query.
- Numbers are compared by value to two decimal places. Text is compared case-insensitively.
- Full result credit requires an exact match. Row order does not affect correctness, because several reference queries sort on keys with ties. Partially correct results earn a small bonus for rows already in the reference position.
- A query is **correct** when its rows match exactly and all expected columns are present. Correctness ends the episode. A correct query scores 0.92–1.00, depending on its style points.
- Task-dependent style bonuses, such as `COALESCE`, are only awarded when the reference query uses them.

## Diagnostics

Each step returns a list of `{type, severity, message, suggestion}` objects:

| Stage | Types |
|---|---|
| Execution | `WRONG_TABLE_NAME`, `WRONG_COLUMN_NAME`, `AMBIGUOUS_COLUMN`, `SYNTAX_ERROR`, `NOT_ALLOWED`, `RESOURCE_LIMIT` |
| Structure | `MISSING_TABLE`, `MISSING_JOIN`, `MISSING_AGGREGATION`, `MISSING_HAVING`, `NULL_HANDLING` |
| Result | `MISSING_COLUMNS`, `EXTRA_COLUMNS`, `MISSING_ROWS`, `EXTRA_ROWS` |
| Behaviour | `DESTRUCTIVE_QUERY`, `REPEATED_QUERY` |

```json
{
  "type": "MISSING_JOIN",
  "severity": "warning",
  "message": "This question requires data from multiple tables, but no JOIN was found.",
  "suggestion": "Use JOIN to combine tables. Example: SELECT ... FROM t1 JOIN t2 ON t1.id = t2.t1_id"
}
```

## Action and observation spaces

**Action:** `SqlQueryAction(query: str)`, a single SQLite `SELECT` statement. `WITH ... SELECT` is allowed.

**Observation** (`SqlQueryObservation`):

| Field | Description |
|---|---|
| `task_id`, `difficulty`, `database_domain` | Task identity |
| `question`, `schema_description` | What to answer, and the schema with relationships and NULL semantics |
| `expected_columns`, `expected_row_count` | Shape of the correct answer |
| `query_result`, `query_error` | Formatted rows (first 20) or the SQLite error |
| `feedback` | Score breakdown, quality notes, issues, and hints as text |
| `diagnostics`, `efficiency_notes` | Structured versions of the feedback |
| `steps_remaining`, `current_score`, `history` | Episode progress: best score so far, previous queries and scores |

## Sandboxing

- **Read-only database.** After seeding, an SQLite authorizer permits only read operations. SQLite itself refuses writes, schema changes, `PRAGMA` and `ATTACH`.
- **Resource limits.** Each query gets 2 seconds and at most 10,000 rows, so runaway queries can't block a server worker.
- **Isolation.** Every episode gets its own in-memory database, and each step accepts exactly one statement.

## Baseline agent

`inference.py` runs an OpenAI-compatible chat model on all 14 tasks. The default is `Qwen/Qwen2.5-72B-Instruct` via the Hugging Face router. It logs each episode in the `[START]` / `[STEP]` / `[END]` format expected by the OpenEnv evaluation pipeline, then prints per-task and per-domain averages.

```bash
export HF_TOKEN="hf_..."                                 # or API_KEY for another provider
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"            # optional
export API_BASE_URL="https://router.huggingface.co/v1"   # optional
uv run python inference.py                               # expects the server on localhost:8000
```

Set `ENV_BASE_URL` to use a remote server, or `IMAGE_NAME` to start the environment from a Docker image.

## Development

```bash
uv sync --extra dev
uv run pytest -q          # grader, sandbox, episode, and consistency tests
uv run ruff check .
uv run openenv validate .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding tasks and deploying to Hugging Face Spaces.

## Project structure

```text
sql_query_env/
├── models.py                         # Action / observation Pydantic models
├── client.py                         # Async WebSocket client (EnvClient)
├── inference.py                      # LLM baseline agent
├── openenv.yaml                      # OpenEnv manifest: tasks, action and observation spaces
├── Dockerfile                        # Container image (HF Spaces, openenv build)
├── server/
│   ├── app.py                        # FastAPI app and `server` entry point
│   ├── sql_query_env_environment.py  # Episode logic: task selection, hints, termination
│   ├── tasks.py                      # Schemas, seed data, read-only DB factory, tasks
│   └── graders.py                    # Execution sandbox, scoring, diagnostics
└── tests/                            # pytest suite
```

## Limitations

- **Guided, not blind.** Diagnostics reveal the reference query's structure: they name its tables and flag a missing `JOIN`, `GROUP BY` or `HAVING`. Scores therefore measure assisted text-to-SQL.
- **Row order is not graded.** Tie-aware order checking would need an explicit sort specification per task.
- **Regex-based table matching.** Table references are extracted without a full SQL parser, so CTE names are not resolved.
- **Small, synthetic data.** Seed tables have 3–24 rows each, and only the SQLite dialect is supported.

## License

Released under the [BSD 3-Clause License](LICENSE).

## Acknowledgements

Built on [OpenEnv](https://github.com/meta-pytorch/OpenEnv) for the Meta PyTorch OpenEnv Hackathon 2026.
