"""CLI entry points — invoked via uv run or installed scripts.

    uv run idra        → production server (port 8000)
    uv run idra-dev    → dev server with --reload (port 8000)
    uv run idra-test   → full pytest test suite
"""

import uvicorn


def serve() -> None:
    """Production server."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)


def serve_dev() -> None:
    """Development server with auto-reload."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


def run_tests() -> None:
    """Run the full pytest suite."""
    import sys
    import pytest
    sys.exit(pytest.main(["tests", "-v"]))
