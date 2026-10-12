# Notes for agents working in this repository

## LLM routing

LLM routing is governed by `ADR-0001` in `omega-specs`. A router decides and
returns the envelope; a provider calls what the envelope names and never
branches on a routing concept. Enforced by `tests/test_architecture_rules.py`.
