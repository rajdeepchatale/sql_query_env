"""Consistency checks for the task set, the manifest, and the baseline script."""

import ast
from pathlib import Path

import pytest
import yaml

from server.tasks import ALL_TASKS_LIST, SCHEMAS, TASK_MAP, create_database

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("task", ALL_TASKS_LIST, ids=lambda t: t.id)
def test_ground_truth_runs_and_matches_expected_columns(task):
    conn = create_database(task.schema_id)
    cursor = conn.execute(task.ground_truth_query)
    columns = [d[0].lower() for d in cursor.description]
    rows = cursor.fetchall()

    assert rows, "reference query must return at least one row"
    assert columns == [c.lower() for c in task.expected_columns]


@pytest.mark.parametrize("task", ALL_TASKS_LIST, ids=lambda t: t.id)
def test_task_metadata(task):
    assert task.difficulty in {"easy", "medium", "hard"}
    assert task.schema_id in SCHEMAS
    assert task.id.startswith(f"{task.schema_id}_{task.difficulty}_")
    assert task.hints, "every task needs at least one hint"
    assert task.max_steps >= 1


def test_task_ids_are_unique():
    ids = [t.id for t in ALL_TASKS_LIST]
    assert len(ids) == len(set(ids))


def test_manifest_lists_every_task():
    manifest = yaml.safe_load((ROOT / "openenv.yaml").read_text())
    manifest_tasks = {t["id"]: t for t in manifest["tasks"]}

    assert set(manifest_tasks) == set(TASK_MAP)
    for task_id, entry in manifest_tasks.items():
        assert entry["difficulty"] == TASK_MAP[task_id].difficulty
        assert entry["domain"] == TASK_MAP[task_id].schema_id


def test_baseline_script_covers_every_task():
    tree = ast.parse((ROOT / "inference.py").read_text())
    task_ids = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "TASK_IDS" for t in node.targets)
    )
    assert sorted(task_ids) == sorted(TASK_MAP)
