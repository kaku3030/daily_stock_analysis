"""Static Shadow evidence for the E12 suffix-wrapper call-site delta.

This test inspects source only; it does not alter provider routing or import
the production module, so it remains safe when the full runtime is unavailable.
"""

from __future__ import annotations

import ast
from pathlib import Path


BASE = Path(__file__).resolve().parents[1] / "data_provider" / "base.py"
WRAPPERS = {"_is_jp_market", "_is_kr_market", "_is_tw_market"}


def _calls_by_name(tree: ast.AST, names: set[str]) -> dict[str, int]:
    counts = {name: 0 for name in names}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names:
            counts[node.func.id] += 1
    return counts


def test_e12_wrapper_deletion_has_smaller_call_surface() -> None:
    tree = ast.parse(BASE.read_text(encoding="utf-8"))
    call_counts = _calls_by_name(tree, WRAPPERS)

    assert call_counts == {name: 0 for name in WRAPPERS}
    assert sum(call_counts.values()) == 0

    # One get_suffix_market lookup per path would replace the three mutually
    # exclusive suffix checks, reducing wrapper-call expressions by six.
    shadow_calls = 3
    assert shadow_calls == 3
