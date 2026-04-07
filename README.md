# SQL Query Generation Environment

An OpenEnv RL environment that trains AI agents to write SQL queries from natural language questions.

## Motivation

We picked SQL generation because it's something we deal with almost every day in our coursework and internships. Whenever we're working with databases, translating a question like "show me the top customers last month" into actual SQL is surprisingly error-prone — wrong JOINs, missing WHERE clauses, forgetting about NULLs. We figured this would make a solid environment because:

- It's a real task with clear right/wrong answers
- Grading is deterministic (compare query results)
- There's a natural difficulty curve from simple SELECTs to complex JOINs
- Partial credit makes sense (right tables but wrong columns should score > 0)

## How it works

The agent gets a database schema and a natural language question. It writes SQL. We run the query, compare results to ground truth, and return a score from 0 to 1 along with diagnostic feedback.

### Multi-domain testing

We test across three different databases to make sure the agent actually *understands* SQL and isn't just memorizing one schema:

| Domain | Tables | Description |
|--------|--------|-------------|
| Company Analytics | departments, employees, products, customers, orders, reviews | Business intelligence queries |
| Hospital Management | wards, doctors, patients, appointments, medications, prescriptions | Healthcare data |
| E-Commerce Platform | sellers, categories, products, users, orders, order_items, returns | Retail analytics |

### Scoring

We break scoring into five components so the agent always gets useful signal:

| Component | Weight | What it measures |
|-----------|--------|-----------------|
| Syntax | 0.10 | Does the query run at all? |
| Tables | 0.15 | Right tables referenced? |
| Columns | 0.20 | Correct output columns? |
| Results | 0.45 | Do the rows match ground truth? |
| Efficiency | 0.10 | Is it well-written SQL? (aliases, no SELECT *, etc.) |

There's also a -0.10 penalty for destructive SQL (DROP, DELETE) and -0.05 for repeating the same query.

### Diagnostic feedback

Instead of just returning a score, we give structured diagnostics:
- What tables are missing from the query
- Whether a JOIN is needed
- Column name mismatches
- Row count differences
- Efficiency tips (use aliases, avoid SELECT *, handle NULLs)

This is designed for process supervision — the agent should be able to use this feedback to iteratively improve its query within an episode.

## Tasks

14 tasks across three difficulty tiers:

**Easy (4 tasks)** — Single table queries with filters and sorting.

**Medium (4 tasks)** — Multi-table JOINs, GROUP BY, HAVING, aggregations.

**Hard (6 tasks)** — Self-joins, anti-joins, subqueries, temporal grouping, NULL chains. These are meant to push even strong models:
- *Salary vs Manager*: self-join to find employees earning more than their boss
- *Cross-ward prescriptions*: join wards table twice to find prescriptions crossing departments
- *Dead stock*: LEFT JOIN + IS NULL anti-pattern for products never ordered
- *Return rate by category*: subquery with COALESCE and division-by-zero handling

### Progressive hints

When the agent gets stuck, we progressively reveal more hints on each failed attempt. First attempt gets a general hint, later attempts get more specific guidance about table structure.

## Getting started

```bash
# install dependencies
uv sync

# start the environment server
uv run server

# run the baseline agent (needs HuggingFace token)
export HF_TOKEN="your-token"
python inference.py
```

## Client example

```python
import asyncio
from sql_query_env import SqlQueryAction, SqlQueryEnv

async def main():
    async with SqlQueryEnv(base_url="http://localhost:8000") as client:
        result = await client.reset()
        print(result.observation.question)
        print(result.observation.schema_description)

        result = await client.step(
            SqlQueryAction(query="SELECT name, salary FROM employees ORDER BY salary DESC")
        )
        print(f"Score: {result.reward}")
        print(f"Feedback: {result.observation.feedback}")

        for diag in result.observation.diagnostics:
            print(f"  [{diag['type']}] {diag['message']}")

asyncio.run(main())
```

## Docker

```bash
docker build -t sql_query_env:latest -f server/Dockerfile .
docker run -p 8000:8000 sql_query_env:latest
```

## Project structure

```
sql_query_env/
├── models.py                 # Action/Observation Pydantic models
├── client.py                 # EnvClient for WebSocket connection
├── inference.py              # Baseline inference script
├── openenv.yaml              # Environment manifest (tasks, schemas)
└── server/
    ├── app.py                # FastAPI entry point
    ├── sql_query_env_environment.py  # Core environment logic
    ├── tasks.py              # Database schemas + all task definitions
    ├── graders.py            # 5-component grading + diagnostics
    └── Dockerfile            # Container build
```

## License

BSD-3-Clause
