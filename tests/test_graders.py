"""Behavioural tests for the grader: correctness, sandboxing, and anti-gaming."""

import time

import pytest

from server import graders
from server.graders import grade_query
from server.tasks import ALL_TASKS_LIST, TASK_MAP, create_database


def _grade(task_id, query, previous=None):
    task = TASK_MAP[task_id]
    return grade_query(create_database(task.schema_id), query, task, previous or [])


@pytest.mark.parametrize("task", ALL_TASKS_LIST, ids=lambda t: t.id)
def test_reference_query_is_graded_correct(task):
    result = grade_query(create_database(task.schema_id), task.ground_truth_query, task, [])

    assert result.is_correct
    assert result.result_score == pytest.approx(0.45)
    assert result.total_score >= 0.9


def test_unrelated_query_scores_low():
    result = _grade("company_easy_1", "SELECT 1")

    assert not result.is_correct
    assert result.total_score <= 0.15


def test_row_order_does_not_block_correctness():
    task = TASK_MAP["company_easy_1"]
    reversed_order = task.ground_truth_query.replace("DESC", "ASC")

    assert _grade("company_easy_1", reversed_order).is_correct


def test_duplicated_rows_are_not_correct():
    task = TASK_MAP["ecommerce_hard_2"]
    body = task.ground_truth_query.split("ORDER BY")[0]
    result = _grade("ecommerce_hard_2", f"{body} UNION ALL {body}")

    assert not result.is_correct
    assert result.result_score < 0.45
    assert "EXTRA_ROWS" in {d.type for d in result.diagnostics}


def test_integer_and_real_values_compare_equal():
    # salary is REAL in the reference; an INTEGER cast must still match
    query = """
        SELECT e.name, CAST(e.salary AS INTEGER) AS salary
        FROM employees e JOIN departments d ON e.department_id = d.id
        WHERE d.name = 'Engineering' AND e.is_active = 1
    """
    assert _grade("company_easy_1", query).is_correct


@pytest.mark.parametrize("query", [
    "DELETE FROM employees",
    "DROP TABLE employees",
    "UPDATE employees SET salary = 0",
    "INSERT INTO departments VALUES (9, 'X', 1, 'Y')",
])
def test_destructive_queries_are_blocked_and_penalized(query):
    task = TASK_MAP["company_easy_1"]
    conn = create_database(task.schema_id)
    before = conn.execute("SELECT COUNT(*), SUM(salary) FROM employees").fetchone()

    result = grade_query(conn, query, task, [])

    assert result.total_score == 0.0
    assert result.penalty == pytest.approx(-0.10)
    assert "DESTRUCTIVE_QUERY" in {d.type for d in result.diagnostics}
    assert conn.execute("SELECT COUNT(*), SUM(salary) FROM employees").fetchone() == before


@pytest.mark.parametrize("query", [
    "PRAGMA table_info(employees)",
    "ATTACH DATABASE ':memory:' AS probe",
    "REPLACE INTO departments VALUES (1, 'X', 1, 'Y')",
])
def test_database_rejects_non_read_statements(query):
    result = _grade("company_easy_1", query)

    assert result.total_score == 0.0
    assert result.error
    assert result.diagnostics


def test_keywords_inside_literals_are_not_destructive():
    query = "SELECT name, salary FROM employees WHERE email LIKE '%update%' -- drop later"
    result = _grade("company_easy_1", query)

    assert result.penalty == 0.0
    assert result.error is None


def test_runaway_query_is_interrupted(monkeypatch):
    monkeypatch.setattr(graders, "QUERY_TIMEOUT_S", 0.2)
    query = "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r) SELECT COUNT(*) FROM r"

    start = time.monotonic()
    result = _grade("company_easy_1", query)

    assert time.monotonic() - start < 5
    assert "RESOURCE_LIMIT" in {d.type for d in result.diagnostics}


def test_oversized_result_is_rejected():
    query = "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r) SELECT x FROM r"
    result = _grade("company_easy_1", query)

    assert "RESOURCE_LIMIT" in {d.type for d in result.diagnostics}


def test_repeated_query_is_penalized():
    query = "SELECT name, salary FROM employees"
    result = _grade("company_easy_1", query, previous=[query.lower()])

    assert result.penalty == pytest.approx(-0.05)
    assert "REPEATED_QUERY" in {d.type for d in result.diagnostics}


def test_penalty_diagnostics_survive_execution_errors():
    query = "SELECT nme FROM employees"
    result = _grade("company_easy_1", query, previous=[query])

    types = {d.type for d in result.diagnostics}
    assert {"REPEATED_QUERY", "WRONG_COLUMN_NAME"} <= types


def test_coalesce_bonus_only_when_task_needs_it():
    query = """
        SELECT COALESCE(p.name, '') AS name, p.price AS price
        FROM products p
        WHERE p.category = 'Electronics' AND p.price > 50
        ORDER BY p.price
    """
    result = _grade("company_easy_2", query)

    assert result.is_correct
    assert not any("COALESCE" in note for note in result.efficiency_notes)


def test_comma_join_tables_are_detected():
    query = """
        SELECT e.name, e.salary FROM employees e, departments d
        WHERE e.department_id = d.id AND d.name = 'Engineering' AND e.is_active = 1
    """
    result = _grade("company_easy_1", query)

    assert result.table_score == pytest.approx(0.15)
    assert "MISSING_TABLE" not in {d.type for d in result.diagnostics}
