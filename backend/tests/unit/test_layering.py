"""Architecture rule (docs/design/01 §1): domain/ imports only the standard library."""

import ast
import sys
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[2] / "src" / "finassist" / "domain"


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0], node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import inside domain is fine
                continue
            yield (node.module or "").split(".")[0], node.lineno


def test_domain_has_files():
    assert list(DOMAIN.glob("*.py")), "domain package not found"


def test_domain_imports_stdlib_only():
    allowed = set(sys.stdlib_module_names) | {"__future__"}
    bad = []
    for f in DOMAIN.glob("*.py"):
        for mod, line in _imports(f):
            if mod == "finassist":
                # only finassist.domain.* allowed
                src = f.read_text(encoding="utf-8").splitlines()[line - 1]
                if "finassist.domain" not in src:
                    bad.append(f"{f.name}:{line} {src.strip()}")
            elif mod not in allowed:
                bad.append(f"{f.name}:{line} imports {mod}")
    assert not bad, bad
