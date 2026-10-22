# Phase 1 LLM routing

The installer keeps its role-keyed `router_catalog` and passes its JSON into the
container as the argument `router_catalog=...`. It passes `router=default` for routine
and premium, and `router=none` for a single provider. Existing installer prompts,
embedding selection, and the debug display are unchanged.

The container entrypoint creates one nginx route per role, including its own API
key and API URL, and writes a credential-free catalog for the harness. The harness
starts one provider instance per record. Instances can use the same provider with
different models, keys, or custom URLs. The default router looks up its chosen
record and returns its provider and model, plus role metadata. The harness
validates that selection against the catalog and dispatches it. Providers make
no routing decisions. A routine-only catalog bypasses router calls entirely.
With `router=none`, only the first catalog record is recognized, in catalog order.
Later records are ignored when preparing gateway routes and starting providers.

## Standalone configuration

Set `router_catalog_file` in `config/config.yaml` to a JSON file, or define
`router_catalog` directly in that YAML file. Both the installer's dictionary and
this LiteLLM-style `model_list` form are accepted:

```yaml
router: default
router_catalog:
  model_list:
    - model_name: routine
      provider: OpenAI
      litellm_params:
        model: openai/your-routine-model
        api_key: os.environ/OPENAI_API_KEY
    - model_name: premium
      provider: Anthropic
      litellm_params:
        model: anthropic/your-premium-model
        api_key: os.environ/ANTHROPIC_API_KEY
```

Provide the referenced environment variables at startup. An optional
`litellm_params.api_base` supplies an API URL. The explicit `provider` identifies
Omega's provider plugin, including `ASICloud`, `ASIOne`, `OpenRouter`, and
`OpenAIAPI`. If omitted, the standard `openai/`, `anthropic/`, and `openrouter/`
model prefixes identify their corresponding providers. A standalone run without
the Docker entrypoint uses the same catalog and the referenced local credentials.
Existing standalone `provider`/`model` settings still create one routine record.

The interchange records use `model_name` for the role and `litellm_params` for
model/credential/base-URL settings. Omega also carries provider and gateway
metadata; this is preparation for LiteLLM, not a LiteLLM gateway implementation.

## Default policy

`default.metta` selects premium when user/tool text contains a configured keyword
(by default `premium`, `premium_model`, `alert_failure`, `alert_failed`, or `error`),
when different senders appear in channel text, when the previous call failed, or
when user-plus-tool messages reach `router_escalate_items` (default 9).

`deep_reasoning` in newly added user/tool text selects premium for
`router_premium_turns` calls (default 3), including the triggering call. Keeping
that message in conversation history does not renew the hold. Sender detection
recognizes the existing IRC, Slack, and Telegram text formats; arbitrary unlabelled
text has no reliable sender identity. System prompt instructions are excluded
from keyword inspection. Embedding selection remains independent of routing.

## Plugin interface

A router plugin defines `(router $request $catalogue $last_outcome)` and registers
its function using `(registerLLMRouter "name" router)` from `loadOmegaPlugin`.
Add its `.metta` file through `config/plugins.yaml`, with `loader: metta` and
`location: "{REPO}/routers"`. The catalog is a list of named records without
literal API keys. Return a mapping containing `provider`, `model`, and optionally
`role`. The default router includes `role` to distinguish records with the same
provider/model but different keys or URLs. A `(provider, model)` pair is also
accepted if it matches exactly one record. Role-only answers, unknown pairs,
ambiguous pairs, and mismatched role/pair answers are rejected without a provider
call. For example, the default router can return
`{"provider": "OpenAI", "model": "your-model", "role": "routine"}`.

Only `default` can be activated in Phase 1; the registration interface is in place
for Phase 2 plugins. New role records need no schema change. The default policy
uses routine and premium; a future router can select other names. Accounting and
the LiteLLM gateway cutover remain Phase 2 work.
