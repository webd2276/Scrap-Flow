from __future__ import annotations

import ast
from pathlib import Path

LOAD_SCRIPT = Path(__file__).resolve().parents[1] / "load" / "locustfile.py"


def test_load_script_parses_and_defines_a_locust_user() -> None:
    source = LOAD_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)

    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    assert "ScrapeFlowUser" in classes
    user = classes["ScrapeFlowUser"]
    bases = [getattr(base, "id", "") for base in user.bases]
    assert "HttpUser" in bases

    tasks = [
        node
        for node in user.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Call) and getattr(decorator.func, "id", "") == "task"
            for decorator in node.decorator_list
        )
    ]
    assert len(tasks) >= 5
    assert "LOAD_API_KEY" in source
    assert '"/v1/scrape"' in source


def test_load_script_imports_when_locust_is_installed() -> None:
    import pytest

    pytest.importorskip("locust")
    namespace: dict[str, object] = {}
    exec(  # noqa: S102 - the load script is repository-owned
        compile(LOAD_SCRIPT.read_text(encoding="utf-8"), str(LOAD_SCRIPT), "exec"),
        namespace,
    )
    user = namespace["ScrapeFlowUser"]
    assert getattr(user, "host", "") == "http://127.0.0.1:8000"
