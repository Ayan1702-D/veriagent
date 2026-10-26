"""Initial smoke test so pytest exits 0 on an empty skeleton."""

import veriagent


def test_package_imports() -> None:
    """Verify the top-level veriagent package is importable."""
    assert veriagent is not None
