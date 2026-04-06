"""
Baseline inference script for the SQL Query Environment.

Runs Qwen-72B across all task domains and difficulty levels,
printing results in the [START]/[STEP]/[END] format required
by the OpenEnv evaluation pipeline.

Usage:
    export HF_TOKEN="your-token"
    python inference.py
"""

import asyncio
import os
import textwrap
from typing import List, Optional

from openai import OpenAI

from sql_query_env import SqlQueryAction, SqlQueryEnv

# --- Config ---

IMAGE_NAME = os.getenv("IMAGE_NAME")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"

BENCHMARK = "sql_query_env"
MAX_STEPS_PER_TASK = 6
TEMPERATURE = 0.3
MAX_TOKENS = 500

# one task from each domain at each difficulty level
TASK_IDS = [
    "company_easy_1",
    "hospital_easy_1",
    "ecommerce_easy_1",
    "company_medium_1",
    "hospital_medium_1",
    "ecommerce_medium_1",
    "company_hard_1",
    "hospital_hard_1",
    "ecommerce_hard_1",
    "company_hard_2",      # self-join challenge
    "hospital_hard_2",     # repeat visits
    "ecommerce_hard_2",    # anti-join / dead stock
]

SUCCESS_THRESHOLD = 0.5

# system prompt for the LLM agent
SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert SQL query writer. You are given a database schema and a
    natural language question. Write a correct SQL query to answer it.

    Rules:
    1. Write ONLY valid SQLite SQL SELECT queries
    2. Do NOT use DROP, DELETE, INSERT, UPDATE, ALTER, CREATE
    3. Pay attention to the schema - different databases have different tables
    4. Use appropriate JOINs when data spans multiple tables
    5. Match the expected column names in your output
    6. Use table aliases for clarity (e.g., FROM employees e)
    7. Use column aliases with AS (e.g., SUM(salary) AS total)
    8. Handle NULLs properly with IS NULL / IS NOT NULL / COALESCE
    9. Return ONLY the raw SQL query - no markdown, no explanations
""").strip()


# --- Logging (required format) ---

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    action_clean = action.replace("\n", " ").replace("\r", "").strip()
    if len(action_clean) > 200:
        action_clean = action_clean[:200] + "..."
    error_val = error if error else "null"
    print(
        f"[STEP] step={step} action={action_clean} reward={reward:.2f} "
        f"done={str(done).lower()} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} "
        f"score={score:.2f} rewards={rewards_str}",
        flush=True,
    )


# --- LLM interaction ---

def build_user_prompt(
    question: str, schema: str, feedback: str,
    expected_columns: List[str], expected_row_count: int,
    step: int, history: List[dict], diagnostics: List[dict],
    database_domain: str,
) -> str:
    """Build the prompt we send to the model with all available context."""
    history_block = ""
    if history:
        lines = [f"  Step {h['step']}: score={h['score']:.2f} | {h['query']}" for h in history[-3:]]
        history_block = "Previous attempts:\n" + "\n".join(lines)

    diag_block = ""
    if diagnostics:
        lines = [f"  [{d['type']}] {d['message']} -> {d['suggestion']}" for d in diagnostics[-3:]]
        diag_block = "Diagnostics from last attempt:\n" + "\n".join(lines)

    return textwrap.dedent(f"""
DATABASE DOMAIN: {database_domain}

DATABASE SCHEMA:
{schema}

QUESTION: {question}

EXPECTED OUTPUT COLUMNS: {', '.join(expected_columns)}
EXPECTED ROW COUNT: {expected_row_count}

{f'FEEDBACK:{chr(10)}{feedback}' if step > 1 else ''}
{diag_block}
{history_block}

Step {step}: Write a SQL query to answer the question.
Return ONLY the raw SQL query, no markdown.
    """).strip()


def extract_sql(text: str) -> str:
    """Clean up LLM output to get just the SQL."""
    text = text.strip()
    if text.startswith("```sql"):
        text = text[6:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.endswith(";"):
        text = text[:-1].strip()
    return text


def get_sql_query(
    client: OpenAI, question: str, schema: str, feedback: str,
    expected_columns: List[str], expected_row_count: int,
    step: int, history: List[dict], diagnostics: List[dict],
    database_domain: str,
) -> str:
    """Ask the LLM for a SQL query."""
    user_prompt = build_user_prompt(
        question, schema, feedback, expected_columns,
        expected_row_count, step, history, diagnostics, database_domain,
    )

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        raw = (completion.choices[0].message.content or "").strip()
        return extract_sql(raw) if raw else "SELECT 1"
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return "SELECT 1"


# --- Main evaluation loop ---

async def run_task(client: OpenAI, env: SqlQueryEnv, task_id: str) -> float:
    """Run one task, return the best score achieved."""
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        result = await env.reset()
        obs = result.observation

        feedback = obs.feedback
        diagnostics = obs.diagnostics

        for step in range(1, MAX_STEPS_PER_TASK + 1):
            if result.done:
                break

            sql_query = get_sql_query(
                client, obs.question, obs.schema_description, feedback,
                obs.expected_columns, obs.expected_row_count,
                step, obs.history, diagnostics, obs.database_domain,
            )

            result = await env.step(SqlQueryAction(query=sql_query))
            obs = result.observation

            reward = result.reward or 0.0
            done = result.done
            error = obs.query_error

            rewards.append(reward)
            steps_taken = step
            feedback = obs.feedback
            diagnostics = obs.diagnostics

            log_step(step=step, action=sql_query, reward=reward, done=done, error=error)

            if done:
                break

        score = max(rewards) if rewards else 0.0
        score = min(max(score, 0.0), 1.0)
        success = score >= SUCCESS_THRESHOLD

    except Exception as e:
        print(f"[DEBUG] Task {task_id} error: {e}", flush=True)
    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return score


async def main() -> None:
    """Run all tasks and print summary."""
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    if IMAGE_NAME:
        env = await SqlQueryEnv.from_docker_image(IMAGE_NAME)
    else:
        base_url = os.getenv("ENV_BASE_URL", "http://localhost:8000")
        env = SqlQueryEnv(base_url=base_url)

    try:
        async with env:
            scores = []
            for task_id in TASK_IDS:
                score = await run_task(client, env, task_id)
                scores.append(score)

            # print summary
            print(f"\n{'='*50}", flush=True)
            print(f"[SUMMARY] Model: {MODEL_NAME}", flush=True)
            print(f"[SUMMARY] Average score: {sum(scores)/len(scores):.2f}", flush=True)
            print(f"{'='*50}", flush=True)

            domains = {"company": [], "hospital": [], "ecommerce": []}
            for tid, sc in zip(TASK_IDS, scores):
                domain = tid.split("_")[0]
                domains[domain].append(sc)
                print(f"  {tid}: {sc:.2f}", flush=True)

            print(f"\nPer-domain averages:", flush=True)
            for domain, dscores in domains.items():
                avg = sum(dscores) / len(dscores) if dscores else 0
                print(f"  {domain}: {avg:.2f}", flush=True)

    except Exception as e:
        print(f"[DEBUG] Environment connection error: {e}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
