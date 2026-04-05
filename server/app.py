"""
FastAPI server entry point.

Start with:
    uv run --project . server
    uvicorn server.app:app --host 0.0.0.0 --port 8000
"""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:
    raise ImportError(
        "openenv-core is required. Install with: uv sync"
    ) from e

# dual-import fallback for different run modes
try:
    from ..models import SqlQueryAction, SqlQueryObservation
    from .sql_query_env_environment import SqlQueryEnvironment
except (ImportError, ModuleNotFoundError):
    from models import SqlQueryAction, SqlQueryObservation
    from server.sql_query_env_environment import SqlQueryEnvironment


app = create_app(
    SqlQueryEnvironment,
    SqlQueryAction,
    SqlQueryObservation,
    env_name="sql_query_env",
    max_concurrent_envs=256,
)


def main():
    """Entry point for `uv run server` and `openenv serve`."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
