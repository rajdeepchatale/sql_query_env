---
title: SQL Query
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
short_description: Text-to-SQL RL environment with execution-based rewards
tags:
  - openenv
---

# SQL Query

[![CI](https://github.com/rajdeepchatale/sql_query_env/actions/workflows/ci.yml/badge.svg)](https://github.com/rajdeepchatale/sql_query_env/actions/workflows/ci.yml)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
[![Hugging Face Space](https://img.shields.io/badge/%F0%9F%A4%97-Space-yellow.svg)](https://huggingface.co/spaces/rajdeepchatale/sql_query_env)

**SQL Query** is an [OpenEnv](https://github.com/meta-pytorch/OpenEnv) reinforcement-learning environment for **text-to-SQL**. The agent receives a database schema and a question in plain English, then submits SQLite queries. Each query is executed and graded against a reference result. The reward gives partial credit for every part the query gets right, and each step also returns structured diagnostics that say what to fix next.

Built for the Meta PyTorch OpenEnv Hackathon 2026.

## Why this environment

- **Verifiable answers.** Every task has a reference query. Grading executes the agent's query and compares the rows, so it is deterministic and needs no LLM judge.
- **Dense reward.** Five scoring components mean a query with the right tables but a wrong aggregate still earns signal, which binary pass/fail can't give.
- **Feedback an agent can act on.** Typed diagnostics such as `MISSING_JOIN`, `NULL_HANDLING` and `EXTRA_ROWS`, plus hints that get more specific after each failed attempt, support correction within an episode (process supervision).
- **Schemas to read, not memorize.** Three domains with different schemas and 14 tasks, from single-table filters to self-joins, anti-joins, and division-by-zero edge cases.
- **Safe to point an agent at.** The database is read-only, and every query runs under a time limit and a row limit.

## How an episode works

1. `reset()` picks a task, or `reset(task_id=...)` selects one, and builds a fresh in-memory SQLite database for its domain.
2. The observation contains the schema, the question, the expected output columns and row count, and a first hint.
3. The agent submits `SqlQueryAction(query="SELECT ...")`.
4. The grader executes the query, compares the result with the reference, and returns a reward in `[0, 1]` with feedback and diagnostics.
5. The episode ends when the result matches exactly or the task's attempt budget (5–10) runs out.

## Tasks

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

Penalties: **−0.10** for destructive SQL, which is also rejected without being executed, and **−0.05** for resubmitting an identical query. The total is clamped to `[0, 1]`.

How results are compared:

- Rows are compared as a **multiset**, so rows duplicated by a join fan-out count against the query.
- Numbers are compared by value to two decimal places, so `INTEGER 145000` equals `REAL 145000.0`. Text is compared case-insensitively.
- Full result credit requires an **exact match**. Row order does not affect correctness, because several reference queries sort on keys with ties. For partially correct results, rows already in the reference position earn a small bonus.
- A query counts as **correct** when its rows match exactly and all expected columns are present. Correctness ends the episode, not a score threshold. A correct query scores 0.92–1.00 depending on its style points.
- Style bonuses that depend on the task, such as `COALESCE`, are only awarded when the reference query uses them. Sprinkling them into every query earns nothing.

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
| `diagnostics`, `efficiency_notes` | Structured versions of the above |
| `steps_remaining`, `current_score`, `history` | Episode progress (best score so far, previous queries and scores) |

## Sandboxing

- **Read-only database.** After seeding, an SQLite authorizer allows only read operations. SQLite itself refuses writes, schema changes, `PRAGMA` and `ATTACH`.
- **Resource limits.** Each query gets 2 seconds and at most 10,000 rows, so an unbounded recursive CTE can't block a server worker.
- **Isolation.** Every episode gets its own in-memory database, and each step accepts exactly one statement.

## Quickstart

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/rajdeepchatale/sql_query_env.git
cd sql_query_env
uv sync
uv run server            # serves on http://localhost:8000
```

From Python:

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

With Docker:

```bash
docker build -t sql_query_env .
docker run -p 8000:8000 sql_query_env
```

## Baseline agent

`inference.py` runs an OpenAI-compatible chat model on all 14 tasks. The default is `Qwen/Qwen2.5-72B-Instruct` via the Hugging Face router. The script logs each episode in the `[START]` / `[STEP]` / `[END]` format expected by the OpenEnv evaluation pipeline, then prints per-task and per-domain averages.

```bash
export HF_TOKEN="hf_..."                       # or API_KEY for another provider
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"  # optional
export API_BASE_URL="https://router.huggingface.co/v1"  # optional
uv run python inference.py                     # expects the server on localhost:8000
```

Set `ENV_BASE_URL` to use a remote server, or `IMAGE_NAME` to start the environment from a Docker image.

## Development

```bash
uv sync --extra dev
uv run pytest -q          # grader, sandbox, episode, and consistency tests
uv run ruff check .
uv run openenv validate .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add a task.

## Project structure

```
sql_query_env/
├── models.py                       # Action / observation Pydantic models
├── client.py                       # Async WebSocket client (EnvClient)
├── inference.py                    # LLM baseline agent
├── openenv.yaml                    # OpenEnv manifest: tasks, action and observation spaces
├── Dockerfile                      # Container image (HF Spaces, openenv build)
├── server/
│   ├── app.py                      # FastAPI app and `server` entry point
│   ├── sql_query_env_environment.py  # Episode logic: task selection, hints, termination
│   ├── tasks.py                    # Schemas, seed data, read-only DB factory, task definitions
│   └── graders.py                  # Execution sandbox, 5-component scoring, diagnostics
└── tests/                          # pytest suite
```

## Limitations

- **Diagnostics reveal the reference query's structure.** They name its tables and flag a missing `JOIN`, `GROUP BY` or `HAVING`. That is by design for guided correction, but it means the scores measure *assisted* text-to-SQL, not blind generation.
- **Row order is not graded.** Tie-aware order checking would need an explicit sort specification per task.
- **Table matching is regex-based.** Table references are extracted without a full SQL parser, so CTE names are not resolved.
- **Small, synthetic data, SQLite dialect only.** Seed tables have 3–24 rows each.

## License

BSD 3-Clause. See [LICENSE](LICENSE).

## Acknowledgements

Built on [OpenEnv](https://github.com/meta-pytorch/OpenEnv) for the Meta PyTorch OpenEnv Hackathon 2026.
