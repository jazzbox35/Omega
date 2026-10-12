Verbatim copies of `providers/` used as fixtures by `tests/test_architecture_rules.py`
(the LLM routing architecture checks, `ADR-0001`).

- `providers@030c0144/`: the head of PR #358, the baseline. Both checks must pass on it.
- `providers@193e9f58/`: the head of PR #373. Check 2 must flag its provider-side routing.

Do not edit these files. They pin what the checks were proven against.
