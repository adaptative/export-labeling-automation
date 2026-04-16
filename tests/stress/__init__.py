"""Stress / concurrency / multi-tenancy soak tests (TASK-045, Sprint-16).

All tests in this package are marked ``@pytest.mark.stress`` and excluded
from the default CI run. Opt in locally with::

    pytest -m stress

Or run a specific file::

    pytest tests/stress/test_rule_eval_concurrency.py -m stress
"""
