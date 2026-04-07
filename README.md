---
title: Sql Query Env
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---
# SQL Query Generation Environment
*Built for the Meta PyTorch OpenEnv Hackathon 2026 by Rajdeep Chatale*

An OpenEnv RL environment that trains AI agents to write SQL queries from natural language questions.

## Motivation

I decided to build an SQL generation environment for this hackathon because writing complex SQL is something I struggle with—and learn from—almost every day. Translating a business question like "show me the top customers last month who never returned an item" into actual SQL is surprisingly error-prone. You have to handle wrong JOINs, missing WHERE clauses, and edge cases around NULLs perfectly. 

I designed this to be a strong OpenEnv benchmark because:
- **It's a practical, real-world task** with clear right/wrong answers, not just a toy game.
- **Grading is deterministic** (I actually execute the query securely in-memory and compare the exact row outputs).
- **There's a natural difficulty curve**, scaling from simple SELECTs to brutal anti-joins.
- **Process Supervision is key.** I built a partial-credit system because binary pass/fail gives LLMs terrible learning signals. If an agent gets the tables right but the columns wrong, it deserves partial credit and a hint!

## How I built the workflow

When the environment spins up, the agent receives a raw database schema and a natural language question. It writes SQL. My environment executes that query, compares the resulting dataset to the ground truth dataset, and returns a clamped score from 0.0 to 1.0 along with rich diagnostic feedback to supervise the agent's next step.

### Multi-domain testing

To ensure agents learn general SQL reasoning rather than just memorizing one layout, I generated three distinct database domains:

| Domain | Tables | Description |
|--------|--------|-------------|
| Company Analytics | departments, employees, products, customers, orders, reviews | Business intelligence queries |
| Hospital Management | wards, doctors, patients, appointments, medications, prescriptions | Healthcare data |
| E-Commerce Platform | sellers, categories, products, users, orders, order_items, returns | Retail analytics |

### Action space

The agent submits a single action per step:

| Field | Type | Description |
|-------|------|-------------|
| `query` | string | A SQL SELECT query to execute against the database |

Only SELECT statements are permitted. Destructive operations (DROP, DELETE, INSERT, UPDATE, etc.) are blocked and penalized.

### Observation space

After each step, the agent receives a rich observation:

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Current task identifier |
| `difficulty` | string | easy, medium, or hard |
| `database_domain` | string | Which database domain this task uses |
| `question` | string | Natural language question to answer with SQL |
| `schema_description` | string | Full database schema with table definitions |
| `query_result` | string | Formatted result of the last query |
| `query_error` | string (nullable) | SQL error message, if any |
| `feedback` | string | Detailed grading feedback |
| `diagnostics` | array | Structured error diagnostics: type, severity, message, suggestion |
| `efficiency_notes` | array | SQL best-practice tips based on the submitted query |
| `expected_row_count` | integer | Expected number of result rows |
| `expected_columns` | array | Expected column names |
| `steps_remaining` | integer | Attempts left in this episode |
| `current_score` | number | Best score so far (0.0–1.0) |
| `history` | array | Previous queries and scores |

### Scoring Structure

I broke the scoring down into five distinct components so the agent always receives a highly dense learning signal, even on failure:

| Component | Weight | What it measures |
|-----------|--------|-----------------|
| Syntax | 0.10 | Does the query run at all? |
| Tables | 0.15 | Right tables referenced? |
| Columns | 0.20 | Correct output columns? |
| Results | 0.45 | Do the rows match ground truth? |
| Efficiency | 0.10 | Is it well-written SQL? (aliases, no SELECT *, etc.) |

There's also a -0.10 penalty for destructive SQL (DROP, DELETE) and -0.05 for repeating the same query.

All scores are clamped to the range **[0.0, 1.0]**.

### Diagnostic feedback

Instead of just returning an arbitrary score, I engineered the grader to emit structured, actionable diagnostics back to the LLM:
- What exact tables are missing from the query
- Whether a JOIN is needed
- Column name mismatches
- Row count differences
- Efficiency tips (use aliases, avoid SELECT *, handle NULLs)

I designed this specifically to excel at **process supervision**. The agent should be able to parse this feedback array and iteratively correct its SQL logic within a single episode.

## Tasks

14 tasks across three difficulty tiers and three database domains:

### Full task list

| Task ID | Domain | Difficulty | Description | Challenge Type |
|---------|--------|-----------|-------------|---------------|
| `company_easy_1` | Company | Easy | List active Engineering employees sorted by salary | Filter + sort |
| `company_easy_2` | Company | Easy | Filter electronics products by price | Single table filter |
| `hospital_easy_1` | Hospital | Easy | List patients still admitted (NULL discharge date) | NULL handling |
| `ecommerce_easy_1` | E-Commerce | Easy | List premium users with signup details | Simple filter |
| `company_medium_1` | Company | Medium | Total revenue per product category for completed orders | JOIN + GROUP BY |
| `company_medium_2` | Company | Medium | Departments with average salary exceeding $100K | GROUP BY + HAVING |
| `hospital_medium_1` | Hospital | Medium | Total medication cost for admitted patients | Multi-table JOIN + aggregation |
| `ecommerce_medium_1` | E-Commerce | Medium | Revenue per seller for delivered orders | JOIN + GROUP BY |
| `company_hard_1` | Company | Hard | Department salary-to-budget utilization percentage | Computed columns |
| `company_hard_2` | Company | Hard | Employees earning more than their direct manager | Self-join |
| `hospital_hard_1` | Hospital | Hard | Doctors prescribing to patients outside their ward | Double-join on wards |
| `hospital_hard_2` | Hospital | Hard | Patients with multiple appointments with the same doctor | GROUP BY + HAVING + COUNT |
| `ecommerce_hard_1` | E-Commerce | Hard | Return rate per product category with edge cases | Subquery + COALESCE |
| `ecommerce_hard_2` | E-Commerce | Hard | In-stock products that have never been ordered | LEFT JOIN anti-join |

### Progressive hints

When the agent gets stuck, my environment progressively reveals more helpful hints on each failed attempt. The first failure triggers a general hint, while later attempts reveal much more specific guidance about table relationships and edge cases.

## Baseline scores

Baseline agent: **Qwen/Qwen2.5-72B-Instruct** via Hugging Face Inference API.

| Task ID | Difficulty | Baseline Score |
|---------|-----------|---------------|
| `company_easy_1` | Easy | 0.90 |
| `company_easy_2` | Easy | 0.90 |
| `hospital_easy_1` | Easy | 0.90 |
| `ecommerce_easy_1` | Easy | 0.85 |
| `company_medium_1` | Medium | 0.75 |
| `company_medium_2` | Medium | 0.70 |
| `hospital_medium_1` | Medium | 0.65 |
| `ecommerce_medium_1` | Medium | 0.70 |
| `company_hard_1` | Hard | 0.55 |
| `company_hard_2` | Hard | 0.45 |
| `hospital_hard_1` | Hard | 0.40 |
| `hospital_hard_2` | Hard | 0.50 |
| `ecommerce_hard_1` | Hard | 0.35 |
| `ecommerce_hard_2` | Hard | 0.45 |

**Average score: ~0.65** | Easy: ~0.89 | Medium: ~0.70 | Hard: ~0.45

*Scores are approximate and may vary slightly between runs due to LLM temperature.*

## Getting started

### Environment variables

Before running the inference script, set these required variables:

```bash
export HF_TOKEN="your-huggingface-token"
export API_BASE_URL="https://router.huggingface.co/v1"   # default
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"            # default
```

### Running locally

```bash
# install dependencies
uv sync

# start the environment server
uv run server

# run the baseline agent
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
docker build -t sql_query_env:latest .
docker run -p 8000:8000 sql_query_env:latest
```

## Project structure

```
sql_query_env/
├── Dockerfile                # Container build
├── models.py                 # Action/Observation Pydantic models
├── client.py                 # EnvClient for WebSocket connection
├── inference.py              # Baseline inference script
├── openenv.yaml              # Environment manifest (tasks, schemas)
└── server/
    ├── app.py                # FastAPI entry point
    ├── sql_query_env_environment.py  # Core environment logic
    ├── tasks.py              # Database schemas + all task definitions
    └── graders.py            # 5-component grading + diagnostics
```

## License

BSD-3-Clause
