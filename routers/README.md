# Routers

A router decides which model an LLM request goes to and returns the completed
envelope. It holds no credential and makes no call. Governed by `ADR-0001`
(`omega-specs`); the boundary is enforced by `tests/test_architecture_rules.py`.

A router is a MeTTa function `(router $request $catalogue $last_outcome)`
returning a `(provider model)` pair, registered from the plugin's
`loadOmegaPlugin` with `(registerLLMRouter "<name>" <function>)`. Adding one
takes a `.metta` file here and an entry in `config/plugins.yaml`
(`loader: metta`, `location: "{REPO}/routers"`), nothing under `src/` or
`providers/`. See `docs/reference-plugin-api.md`.
