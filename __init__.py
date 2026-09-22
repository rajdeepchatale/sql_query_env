"""SQL Query Generation Environment."""

# The repo root doubles as the `sql_query_env` package (OpenEnv layout). Only
# re-export when imported as that package: tools that load this file as a bare
# module (e.g. pytest in a checkout named `sql_query_env-main`) have no parent
# package for the relative imports to resolve against.
if __package__:
    from .client import SqlQueryEnv
    from .models import SqlQueryAction, SqlQueryObservation

__all__ = [
    "SqlQueryAction",
    "SqlQueryObservation",
    "SqlQueryEnv",
]
