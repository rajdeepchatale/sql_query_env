"""
Grading logic for SQL queries.

Scoring is split into five components instead of binary pass/fail. With a
binary reward, a query that references the right tables but gets one
aggregate column wrong scores the same as garbage, which gives an agent no
gradient to follow. Partial credit keeps the signal dense:

  syntax=0.10, tables=0.15, columns=0.20, results=0.45, efficiency=0.10

Result correctness dominates, so a query has to return mostly correct rows
to score above ~0.70. A query only counts as *correct* (and ends the
episode) when its rows match the reference result exactly.

Agent queries run under a time and row budget against a read-only
connection (see ``tasks.create_database``).
"""

import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .tasks import Task

# Execution budget for a single agent query. The seed data is tiny, so any
# legitimate query finishes in milliseconds; these limits only stop runaway
# queries (e.g. an unbounded recursive CTE) from blocking a server worker.
QUERY_TIMEOUT_S = 2.0
MAX_RESULT_ROWS = 10_000
_PROGRESS_INTERVAL = 10_000  # SQLite VM instructions between deadline checks
_LIMIT_PREFIX = "Resource limit exceeded"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Diagnostic:
    """Structured diagnostic for process supervision feedback."""
    type: str       # e.g. MISSING_JOIN, WRONG_TABLE_NAME
    severity: str   # error / warning / info
    message: str
    suggestion: str

    def to_dict(self) -> Dict:
        return {
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class GradeResult:
    """Holds all scoring info for a single query attempt."""

    total_score: float
    syntax_score: float
    table_score: float
    column_score: float
    result_score: float
    efficiency_score: float
    penalty: float
    feedback: str
    query_result: Optional[str]
    error: Optional[str]
    rows_returned: int
    rows_expected: int
    diagnostics: List[Diagnostic] = field(default_factory=list)
    efficiency_notes: List[str] = field(default_factory=list)
    # True when the returned rows match the reference result exactly and all
    # expected columns are present. Independent of the efficiency score.
    is_correct: bool = False


class QueryLimitError(Exception):
    """Raised when an agent query exceeds the time or row budget."""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _extract_tables(query: str) -> Set[str]:
    """Pull table names out of FROM and JOIN clauses.

    Regex-based rather than a full parser: handles comma-separated FROM lists
    and subqueries, but not CTE names. Good enough for the task set without
    adding a dependency on sqlparse.
    """
    q = " ".join(query.lower().split())
    tables = set()
    from_list = r'\bfrom\s+(\w+(?:\s+(?:as\s+)?\w+)?(?:\s*,\s*\w+(?:\s+(?:as\s+)?\w+)?)*)'
    for match in re.finditer(from_list, q):
        for item in match.group(1).split(","):
            tables.add(item.split()[0])
    for match in re.finditer(r'\bjoin\s+(\w+)', q):
        tables.add(match.group(1))
    return tables


def _format_result(rows: List[Tuple], columns: List[str], max_rows: int = 20) -> str:
    """Pretty-print query results."""
    if not rows:
        return "(no rows returned)"

    lines = []
    header = " | ".join(columns)
    lines.append(header)
    lines.append("-" * len(header))

    for row in rows[:max_rows]:
        lines.append(" | ".join(str(v) for v in row))
    if len(rows) > max_rows:
        lines.append(f"... ({len(rows) - max_rows} more rows)")

    return "\n".join(lines)


def _is_destructive(query: str) -> bool:
    """Check whether a query tries to modify data or schema.

    String literals and comments are stripped first so that e.g.
    ``WHERE notes LIKE '%update%'`` is not flagged. This check only decides
    the penalty; the read-only authorizer on the connection is what actually
    prevents writes.
    """
    q = re.sub(r"'(?:[^']|'')*'", "''", query)
    q = re.sub(r"--[^\n]*|/\*.*?\*/", " ", q, flags=re.DOTALL).upper()
    bad_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE", "INSERT", "CREATE"]
    for kw in bad_keywords:
        if re.search(rf'\b{kw}\b', q):
            return True
    return False


def _run_query(conn: sqlite3.Connection, query: str) -> Tuple[List[str], List[Tuple]]:
    """Execute an agent query under the time and row budget.

    Returns lower-cased column names and the fetched rows. Raises
    ``QueryLimitError`` when a budget is exceeded and ``sqlite3.Error`` (or
    ``ValueError`` for statements without a result set) otherwise.
    """
    deadline = time.monotonic() + QUERY_TIMEOUT_S
    conn.set_progress_handler(lambda: time.monotonic() > deadline, _PROGRESS_INTERVAL)
    cursor = None
    try:
        cursor = conn.execute(query)
        if cursor.description is None:
            raise ValueError("Query did not return a result set. Submit a SELECT statement.")
        columns = [desc[0].lower() for desc in cursor.description]
        rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
    except sqlite3.OperationalError as e:
        if str(e) == "interrupted":
            raise QueryLimitError(
                f"{_LIMIT_PREFIX}: query ran longer than {QUERY_TIMEOUT_S:g}s."
            ) from e
        raise
    finally:
        conn.set_progress_handler(None, 0)
        if cursor is not None:
            cursor.close()

    if len(rows) > MAX_RESULT_ROWS:
        raise QueryLimitError(f"{_LIMIT_PREFIX}: query returned more than {MAX_RESULT_ROWS} rows.")
    return columns, rows


def _normalize_value(v) -> str:
    """Normalize cell values for comparison.

    Numbers are compared by value at 2 decimal places, so 3.1000001 matches
    3.10 and an INTEGER 145000 matches a REAL 145000.0. Text is compared
    case-insensitively.
    """
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return f"{float(v):.2f}"
    return str(v).strip().lower()


def _compare_result_sets(
    actual_rows: List[Tuple],
    expected_rows: List[Tuple],
    ground_truth_query: str = "",
) -> Tuple[float, bool]:
    """Compare actual vs expected rows.

    Returns ``(similarity, exact_match)``. Rows are compared as multisets, so
    duplicated rows (e.g. from join fan-out) count against the query. Row
    order does not affect an exact match: several reference queries sort on
    keys with ties, where any tie order is equally valid. For partially
    correct results, rows in the reference position earn a small bonus.
    """
    if not expected_rows:
        return (1.0, True) if not actual_rows else (0.0, False)
    if not actual_rows:
        return 0.0, False

    def normalize_row(row: Tuple) -> Tuple[str, ...]:
        return tuple(_normalize_value(v) for v in row)

    actual_norm = [normalize_row(r) for r in actual_rows]
    expected_norm = [normalize_row(r) for r in expected_rows]

    actual_counts = Counter(actual_norm)
    expected_counts = Counter(expected_norm)
    if actual_counts == expected_counts:
        return 1.0, True

    matching = sum((actual_counts & expected_counts).values())
    total_expected = len(expected_norm)

    # what fraction of expected rows did we get?
    content_score = matching / total_expected

    # dock points for extra rows the agent shouldn't have returned
    extra = len(actual_norm) - matching
    if extra > 0:
        content_score = max(0.0, content_score - min(extra / total_expected * 0.3, 0.3))

    # small bonus for rows already in the right position when ORDER BY is expected
    order_bonus = 0.0
    has_order = "ORDER BY" in ground_truth_query.upper()
    if has_order and content_score > 0.5 and len(actual_norm) == len(expected_norm):
        correct_positions = sum(
            1 for a, e in zip(actual_norm, expected_norm, strict=True) if a == e
        )
        order_bonus = (correct_positions / len(expected_norm)) * 0.1

    # full credit is reserved for an exact match
    return min(content_score + order_bonus, 0.95), False


# ---------------------------------------------------------------------------
# Diagnostic engine
# ---------------------------------------------------------------------------

def _diagnose_query(
    query: str,
    task: Task,
    actual_rows: List[Tuple],
    expected_rows: List[Tuple],
    actual_cols: List[str],
    expected_cols: List[str],
    error: Optional[str],
) -> List[Diagnostic]:
    """Figure out what went wrong and give actionable feedback.

    Covers execution errors (unknown table/column, ambiguous column,
    disallowed statement, resource limits, syntax) and structural mismatches
    against the reference query (missing tables, JOIN, GROUP BY, HAVING,
    NULL handling, columns, row counts). The goal is process supervision:
    give the agent enough information to fix its query on the next attempt.
    """
    diagnostics = []
    q_upper = query.upper()
    gt_upper = task.ground_truth_query.upper()

    # -- execution errors (parsed from SQLite error messages) --
    if error:
        err_lower = error.lower()
        if "no such table" in err_lower:
            table_match = re.search(r'no such table: (\w+)', error, re.IGNORECASE)
            table_name = table_match.group(1) if table_match else "unknown"
            diagnostics.append(Diagnostic(
                type="WRONG_TABLE_NAME",
                severity="error",
                message=f"Table '{table_name}' does not exist in this database.",
                suggestion="Check the schema description for available table names.",
            ))
        elif "no such column" in err_lower:
            col_match = re.search(r'no such column: (\S+)', error, re.IGNORECASE)
            col_name = col_match.group(1) if col_match else "unknown"
            diagnostics.append(Diagnostic(
                type="WRONG_COLUMN_NAME",
                severity="error",
                message=f"Column '{col_name}' does not exist.",
                suggestion="Check the table definition for correct column names.",
            ))
        elif "ambiguous column" in err_lower:
            diagnostics.append(Diagnostic(
                type="AMBIGUOUS_COLUMN",
                severity="error",
                message="A column name is ambiguous - it exists in multiple tables.",
                suggestion="Use table aliases (e.g. e.name instead of just name).",
            ))
        elif "not authorized" in err_lower:
            diagnostics.append(Diagnostic(
                type="NOT_ALLOWED",
                severity="error",
                message="The database is read-only; this statement is not allowed.",
                suggestion="Submit a single SELECT statement (WITH ... SELECT is fine).",
            ))
        elif error.startswith(_LIMIT_PREFIX):
            diagnostics.append(Diagnostic(
                type="RESOURCE_LIMIT",
                severity="error",
                message=error,
                suggestion="Check for unbounded recursion or an accidental cross join.",
            ))
        else:
            diagnostics.append(Diagnostic(
                type="SYNTAX_ERROR",
                severity="error",
                message=f"SQL syntax error: {error[:100]}",
                suggestion="Check your SQL syntax. Common issues: missing commas, unmatched parentheses, typos.",
            ))
        return diagnostics

    # -- structural checks --
    expected_tables = _extract_tables(task.ground_truth_query)
    actual_tables = _extract_tables(query)

    missing_tables = expected_tables - actual_tables
    if missing_tables:
        diagnostics.append(Diagnostic(
            type="MISSING_TABLE",
            severity="warning",
            message=f"Your query doesn't reference: {', '.join(sorted(missing_tables))}",
            suggestion=f"You probably need to JOIN with {', '.join(sorted(missing_tables))} to get the required data.",
        ))

    if "JOIN" in gt_upper and "JOIN" not in q_upper:
        diagnostics.append(Diagnostic(
            type="MISSING_JOIN",
            severity="warning",
            message="This question requires data from multiple tables, but no JOIN was found.",
            suggestion="Use JOIN to combine tables. Example: SELECT ... FROM t1 JOIN t2 ON t1.id = t2.t1_id",
        ))

    if "GROUP BY" in gt_upper and "GROUP BY" not in q_upper:
        diagnostics.append(Diagnostic(
            type="MISSING_AGGREGATION",
            severity="warning",
            message="This question requires grouping/aggregation, but no GROUP BY was found.",
            suggestion="Use GROUP BY with aggregate functions (SUM, COUNT, AVG) to group results.",
        ))

    if "HAVING" in gt_upper and "HAVING" not in q_upper and "GROUP BY" in q_upper:
        diagnostics.append(Diagnostic(
            type="MISSING_HAVING",
            severity="info",
            message="You might need a HAVING clause to filter grouped results.",
            suggestion="HAVING filters after GROUP BY. Example: HAVING COUNT(*) > 5",
        ))

    if "IS NULL" in gt_upper and "IS NULL" not in q_upper:
        diagnostics.append(Diagnostic(
            type="NULL_HANDLING",
            severity="warning",
            message="This question involves NULL values. Use IS NULL or IS NOT NULL.",
            suggestion="In SQL, NULL != NULL. Use IS NULL to check for missing values, not = NULL.",
        ))

    # -- result set checks --
    missing_cols = sorted(set(expected_cols) - set(actual_cols))
    if missing_cols:
        diagnostics.append(Diagnostic(
            type="MISSING_COLUMNS",
            severity="warning",
            message=f"Missing output columns: {', '.join(missing_cols)}",
            suggestion=f"Add these to your SELECT: {', '.join(missing_cols)}",
        ))

    extra_cols = sorted(set(actual_cols) - set(expected_cols))
    if extra_cols:
        diagnostics.append(Diagnostic(
            type="EXTRA_COLUMNS",
            severity="info",
            message=f"Extra columns in output: {', '.join(extra_cols)}",
            suggestion=f"Expected columns are: {', '.join(expected_cols)}",
        ))

    if len(actual_rows) > len(expected_rows):
        diagnostics.append(Diagnostic(
            type="EXTRA_ROWS",
            severity="warning",
            message=f"Got {len(actual_rows)} rows but expected {len(expected_rows)}.",
            suggestion="Your WHERE/HAVING conditions may be too broad, or a JOIN is duplicating rows.",
        ))
    elif len(actual_rows) < len(expected_rows) and len(actual_rows) > 0:
        diagnostics.append(Diagnostic(
            type="MISSING_ROWS",
            severity="warning",
            message=f"Got {len(actual_rows)} rows but expected {len(expected_rows)}.",
            suggestion="Filters might be too restrictive, or try LEFT JOIN instead of INNER JOIN.",
        ))

    return diagnostics


# ---------------------------------------------------------------------------
# Efficiency scoring
# ---------------------------------------------------------------------------

def _score_efficiency(
    query: str,
    task: Task,
    actual_cols: List[str],
    expected_cols: List[str],
) -> Tuple[float, List[str]]:
    """Score SQL best practices (0.0 - 0.10).

    Rewards good habits and penalizes bad ones. The weights are small
    (max 0.10 total) so style never outweighs correctness. Bonuses that
    depend on the task (COALESCE, DISTINCT) are judged against the reference
    query, so they can't be farmed by adding the construct everywhere.
    """
    notes = []
    score = 0.0
    q_upper = query.upper().strip()
    gt_upper = task.ground_truth_query.upper()

    # -- good practices --
    if re.search(r'\bAS\s+\w+', query, re.IGNORECASE):
        score += 0.03
        notes.append("Good: using column aliases (AS)")

    if "SELECT *" not in q_upper and len(expected_cols) > 0:
        if set(actual_cols).issuperset(set(expected_cols)):
            score += 0.02
            notes.append("Good: selecting specific columns instead of SELECT *")

    alias_pattern = r'\b(?:FROM|JOIN)\s+\w+\s+(?:AS\s+)?([a-z]\w{0,2})\b'
    if re.search(alias_pattern, query, re.IGNORECASE):
        score += 0.02
        notes.append("Good: using table aliases for readability")

    null_funcs = r'\bCOALESCE\b|\bIFNULL\b'
    if re.search(null_funcs, query, re.IGNORECASE) and re.search(null_funcs, gt_upper):
        score += 0.03
        notes.append("Good: proper NULL handling with COALESCE/IFNULL")

    # -- bad practices --
    if "SELECT *" in q_upper and len(expected_cols) > 0 and len(expected_cols) < 8:
        score -= 0.02
        notes.append("Avoid SELECT * when you only need specific columns")

    if "DISTINCT" in q_upper and "DISTINCT" not in gt_upper:
        score -= 0.01
        notes.append("DISTINCT may not be needed here - check if duplicates are actually expected")

    # check for cartesian product (FROM a, b without JOIN)
    from_tables = re.findall(r'\bFROM\s+(\w+(?:\s*,\s*\w+)+)', query, re.IGNORECASE)
    if from_tables and "JOIN" not in q_upper:
        score -= 0.02
        notes.append("Warning: potential Cartesian product - use explicit JOIN instead of comma-separated tables")

    score = max(0.0, min(score, 0.10))
    return score, notes


# ---------------------------------------------------------------------------
# Main grading function
# ---------------------------------------------------------------------------

def _failed_result(
    penalty: float,
    feedback_parts: List[str],
    error: str,
    diagnostics: List[Diagnostic],
) -> GradeResult:
    """Build the result for a query that was blocked or failed to execute."""
    return GradeResult(
        total_score=max(0.0, penalty),
        syntax_score=0.0,
        table_score=0.0,
        column_score=0.0,
        result_score=0.0,
        efficiency_score=0.0,
        penalty=penalty,
        feedback="\n".join(feedback_parts),
        query_result=None,
        error=error,
        rows_returned=0,
        rows_expected=0,
        diagnostics=diagnostics,
        efficiency_notes=[],
    )


def grade_query(
    conn: sqlite3.Connection,
    query: str,
    task: Task,
    previous_queries: List[str],
) -> GradeResult:
    """Grade a submitted SQL query.

    Scoring breakdown:
      syntax:     0.10 (query runs without error)
      tables:     0.15 (correct tables referenced)
      columns:    0.20 (correct output columns)
      results:    0.45 (correct data returned)
      efficiency: 0.10 (query quality)
      penalties: -0.10 for destructive SQL, -0.05 for repeated queries

    Destructive queries are rejected without being executed.
    """
    feedback_parts = []
    syntax_score = 0.0
    table_score = 0.0
    column_score = 0.0
    result_score = 0.0
    efficiency_score = 0.0
    penalty = 0.0
    query_result_str = None
    rows_returned = 0
    rows_expected = 0
    diagnostics = []
    efficiency_notes = []

    # check for destructive queries
    destructive = _is_destructive(query)
    if destructive:
        penalty -= 0.10
        feedback_parts.append("PENALTY: Destructive SQL detected. Only SELECT statements are allowed.")
        diagnostics.append(Diagnostic(
            type="DESTRUCTIVE_QUERY",
            severity="error",
            message="Destructive operations (DROP, DELETE, etc.) are not allowed.",
            suggestion="Use only SELECT statements to query data.",
        ))

    # check for repeated query
    normalized_query = " ".join(query.lower().split())
    for prev in previous_queries:
        if " ".join(prev.lower().split()) == normalized_query:
            penalty -= 0.05
            feedback_parts.append("PENALTY: Identical query submitted before. Try something different.")
            diagnostics.append(Diagnostic(
                type="REPEATED_QUERY",
                severity="warning",
                message="This exact query was already submitted.",
                suggestion="Modify your query based on the previous feedback to improve.",
            ))
            break

    if destructive:
        return _failed_result(
            penalty, feedback_parts,
            "Blocked: only read-only SELECT statements are allowed.", diagnostics,
        )

    # 1. Syntax check (0.10)
    try:
        actual_cols, actual_rows = _run_query(conn, query)
        rows_returned = len(actual_rows)
        syntax_score = 0.10
        feedback_parts.append("Query executed successfully.")
        query_result_str = _format_result(actual_rows, actual_cols)
    except Exception as e:
        error_msg = str(e)
        feedback_parts.append(f"SQL Error: {error_msg}")
        diagnostics.extend(_diagnose_query(query, task, [], [], [], [], error_msg))
        return _failed_result(penalty, feedback_parts, error_msg, diagnostics)

    # get ground truth results
    try:
        expected_rows = conn.execute(task.ground_truth_query).fetchall()
        rows_expected = len(expected_rows)
    except Exception:
        expected_rows = []
        rows_expected = 0

    # 2. Table references (0.15)
    expected_tables = _extract_tables(task.ground_truth_query)
    actual_tables = _extract_tables(query)

    if expected_tables:
        matching_tables = actual_tables & expected_tables
        table_ratio = len(matching_tables) / len(expected_tables)
        table_score = 0.15 * table_ratio

        if table_ratio == 1.0:
            feedback_parts.append("Correct tables referenced.")
        elif table_ratio > 0:
            missing = expected_tables - actual_tables
            feedback_parts.append(f"Partially correct tables. Missing: {', '.join(sorted(missing))}")
        else:
            feedback_parts.append(f"Wrong tables. Consider using: {', '.join(sorted(expected_tables))}")

    # 3. Column check (0.20)
    expected_cols_lower = [c.lower() for c in task.expected_columns]
    col_ratio = 1.0

    if expected_cols_lower:
        matching_cols = set(actual_cols) & set(expected_cols_lower)
        col_ratio = len(matching_cols) / len(expected_cols_lower)
        column_score = 0.20 * col_ratio

        if col_ratio == 1.0:
            feedback_parts.append("Correct output columns.")
        elif col_ratio > 0:
            missing_cols = sorted(set(expected_cols_lower) - set(actual_cols))
            feedback_parts.append(f"Missing columns: {', '.join(missing_cols)}")
        else:
            feedback_parts.append(
                f"Wrong columns. Expected: {', '.join(expected_cols_lower)}. Got: {', '.join(actual_cols)}"
            )

    # 4. Result set comparison (0.45)
    similarity, exact_match = _compare_result_sets(
        actual_rows, expected_rows, task.ground_truth_query
    )
    result_score = 0.45 * similarity

    if exact_match:
        feedback_parts.append("Perfect result set - all rows match.")
    elif similarity > 0.5:
        feedback_parts.append(
            f"Partial match: {similarity:.0%} of expected rows. "
            f"Got {rows_returned} rows, expected {rows_expected}."
        )
    elif similarity > 0:
        feedback_parts.append(
            f"Low match: {similarity:.0%} of expected rows. "
            f"Got {rows_returned} rows, expected {rows_expected}."
        )
    else:
        feedback_parts.append(
            f"No matching rows. Expected {rows_expected} rows, got {rows_returned}."
        )

    # 5. Efficiency (0.10)
    efficiency_score, efficiency_notes = _score_efficiency(
        query, task, actual_cols, expected_cols_lower
    )

    # generate diagnostics
    diagnostics.extend(_diagnose_query(
        query, task, actual_rows, expected_rows,
        actual_cols, expected_cols_lower, None,
    ))

    # compute final score
    total = syntax_score + table_score + column_score + result_score + efficiency_score + penalty
    total = max(0.0, min(total, 1.0))

    # score breakdown
    feedback_parts.append(
        f"\nScore: syntax={syntax_score:.2f} + tables={table_score:.2f} + "
        f"columns={column_score:.2f} + results={result_score:.2f} + "
        f"efficiency={efficiency_score:.2f} + penalties={penalty:.2f} = {total:.2f}"
    )

    if efficiency_notes:
        feedback_parts.append("\nQuery quality notes:")
        feedback_parts.extend(f"  - {note}" for note in efficiency_notes)

    if diagnostics:
        feedback_parts.append("\nIssues found:")
        for d in diagnostics:
            severity_tag = "ERR" if d.severity == "error" else "WARN" if d.severity == "warning" else "INFO"
            feedback_parts.append(f"  [{severity_tag}] {d.type}: {d.message}")
            feedback_parts.append(f"    Suggestion: {d.suggestion}")

    return GradeResult(
        total_score=total,
        syntax_score=syntax_score,
        table_score=table_score,
        column_score=column_score,
        result_score=result_score,
        efficiency_score=efficiency_score,
        penalty=penalty,
        feedback="\n".join(feedback_parts),
        query_result=query_result_str,
        error=None,
        rows_returned=rows_returned,
        rows_expected=rows_expected,
        diagnostics=diagnostics,
        efficiency_notes=efficiency_notes,
        is_correct=exact_match and col_ratio == 1.0,
    )
