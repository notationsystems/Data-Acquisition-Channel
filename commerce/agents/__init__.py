"""Agent implementations.

NOTHING IN THIS PACKAGE MAY CONSTRUCT A COMMITMENT. The rule is enforced
by a source scan in tests/test_commerce_authority.py, not by this
docstring: a boundary that lives only in prose is enforced by whoever last
read it.

An agent here reads evidence, ranks, refuses, and writes `Proposal`
objects to a `ReviewQueue`. It never issues, binds, contacts, submits,
books or files.
"""
