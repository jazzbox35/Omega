# Routers

A router decides which model an LLM request goes to and returns the completed
envelope. It holds no credential and makes no call. Governed by `ADR-0001`
(`omega-specs`); the boundary is enforced by `tests/test_architecture_rules.py`.
