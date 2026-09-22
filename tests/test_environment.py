"""Episode-level tests for SqlQueryEnvironment."""

import pytest

from models import SqlQueryAction
from server.sql_query_env_environment import SqlQueryEnvironment
from server.tasks import TASK_MAP


@pytest.fixture
def env():
    environment = SqlQueryEnvironment()
    yield environment
    environment.close()


def test_reset_selects_requested_task(env):
    obs = env.reset(task_id="hospital_hard_2")

    assert obs.task_id == "hospital_hard_2"
    assert obs.expected_columns == TASK_MAP["hospital_hard_2"].expected_columns
    assert obs.expected_row_count > 0
    assert obs.steps_remaining == TASK_MAP["hospital_hard_2"].max_steps
    assert not obs.done


def test_reset_rejects_unknown_task(env):
    with pytest.raises(ValueError, match="Unknown task_id"):
        env.reset(task_id="company_easy_99")


def test_seeded_resets_are_reproducible():
    def task_order(seed):
        environment = SqlQueryEnvironment()
        return [environment.reset(seed=seed if i == 0 else None).task_id for i in range(5)]

    assert task_order(7) == task_order(7)


def test_unseeded_resets_cycle_through_every_task(env):
    seen = {env.reset().task_id for _ in range(len(TASK_MAP))}

    assert seen == set(TASK_MAP)


def test_correct_answer_ends_episode(env):
    env.reset(task_id="company_easy_2")
    obs = env.step(SqlQueryAction(query=TASK_MAP["company_easy_2"].ground_truth_query))

    assert obs.done
    assert obs.reward >= 0.9
    assert obs.metadata["is_correct"]


def test_episode_ends_when_attempts_run_out(env):
    obs = env.reset(task_id="company_easy_1")
    for i in range(obs.steps_remaining):
        obs = env.step(SqlQueryAction(query=f"SELECT {i}"))

    assert obs.done
    assert obs.steps_remaining == 0


def test_writes_cannot_be_used_to_game_the_reward(env):
    # Deleting every row would make an empty answer "match" the reference.
    env.reset(task_id="company_easy_1")
    obs = env.step(SqlQueryAction(query="DELETE FROM employees"))
    assert obs.reward == 0.0

    obs = env.step(SqlQueryAction(query="SELECT e.name AS name, e.salary AS salary FROM employees e"))
    assert not obs.done
    assert obs.reward < 0.9


def test_dropped_table_does_not_break_the_episode(env):
    env.reset(task_id="ecommerce_hard_1")
    env.step(SqlQueryAction(query="DROP TABLE returns"))
    obs = env.step(SqlQueryAction(query=TASK_MAP["ecommerce_hard_1"].ground_truth_query))

    assert obs.done
    assert obs.metadata["is_correct"]
