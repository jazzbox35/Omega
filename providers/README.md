# Providers

A provider calls the model the LLM request names and never decides which one.
The request's `model`, when set, is sent instead of the configured model; every
provider reads it through `AIProvider.effective_model` (`lib_llm_ext.py`), so
the raw request, the cache key and the log lines agree with the call. A
provider never reads the request's `router` or `metadata`, and `provider`
selects nothing: the call goes to the configured provider.

Governed by `ADR-0001` (`omega-specs`); the boundary is enforced by
`tests/test_architecture_rules.py`. Choosing the model is a router's job: see
`routers/README.md`.
