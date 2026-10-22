"""Phase 1 coverage. Added for review; not executed during implementation."""

import json
from types import SimpleNamespace

import pytest
import config
import providers
import router_policy
from router_catalog import normalize_catalog, prepare_gateway


def record(model, token="test-key", provider="OpenAI"):
    return {"provider": provider, "model": model, "token": token,
            "api_token_var": "OPENAI_API_KEY", "openaiapi_url": ""}


def test_installer_catalog_accepts_additional_roles():
    catalog = normalize_catalog({"routine": record("small"), "premium": record("large"),
                                 "coding": record("code")})
    assert catalog["coding"]["model_name"] == "coding"
    assert catalog["routine"]["litellm_params"]["model"] == "openai/small"


def test_litellm_style_catalog():
    catalog = normalize_catalog({"model_list": [{
        "model_name": "routine", "litellm_params": {
            "model": "anthropic/example", "api_key": "os.environ/EXAMPLE_KEY"}}]})
    assert catalog["routine"]["provider"] == "Anthropic"
    assert catalog["routine"]["model"] == "example"


def test_gateway_separates_same_provider_keys_and_urls(tmp_path):
    raw = {"routine": record("small", "routine-secret"),
           "premium": record("large", "premium-secret")}
    raw["premium"]["openaiapi_url"] = "https://premium.example/v1"
    routes, catalog = tmp_path / "routes", tmp_path / "catalog.json"
    prepare_gateway(raw, routes, catalog)
    assert "location /catalog/routine/" in routes.read_text()
    assert "location /catalog/premium/" in routes.read_text()
    assert "premium.example/v1/" in routes.read_text()
    for secret in ("routine-secret", "premium-secret"):
        assert secret in routes.read_text()
        assert secret not in catalog.read_text()
    assert len(json.loads(catalog.read_text())["model_list"]) == 2


def test_no_router_ignores_later_records_in_gateway(tmp_path):
    raw = {"premium": record("first"), "routine": {"provider": "invalid"}}
    routes, catalog = tmp_path / "routes", tmp_path / "catalog.json"
    prepare_gateway(raw, routes, catalog, first_only=True)
    assert "location /catalog/premium/" in routes.read_text()
    assert "location /catalog/routine/" not in routes.read_text()
    entries = json.loads(catalog.read_text())["model_list"]
    assert [entry["model_name"] for entry in entries] == ["premium"]


def test_no_router_dispatches_first_record_regardless_of_role(monkeypatch):
    monkeypatch.setattr(providers, "_router", "none")
    monkeypatch.setattr(providers, "_catalogue", {
        "premium": {"provider": "OpenAI", "model": "first"}})
    dispatched = []
    monkeypatch.setattr(providers, "_llmProviderChatRecord",
                        lambda req, role, provider, model: dispatched.append((role, provider, model)))
    providers.llmProviderChat(providers.LLMRequest())
    assert dispatched == [("premium", "OpenAI", "first")]


@pytest.fixture
def policy(monkeypatch):
    settings = {"router_premium_turns": 3, "router_escalate_items": 99}
    monkeypatch.setattr(router_policy, "config_get_by_key",
                        lambda key, default=None: settings.get(key, default))
    router_policy.reset()
    yield settings
    router_policy.reset()


def request(*texts):
    return SimpleNamespace(messages=[SimpleNamespace(role="user", content=t) for t in texts])


def test_deep_reasoning_hold_expires_with_historical_trigger(policy):
    req = request("alice: deep_reasoning")
    assert [router_policy.needs_premium(req, None) for _ in range(4)] == [True, True, True, False]


@pytest.mark.parametrize("text", ["ALERT_FAILURE", "ALERT_FAILED", "premium", "error"])
def test_escalation_keywords(policy, text):
    assert router_policy.needs_premium(request(text), None)


@pytest.mark.parametrize("text", ["alice: hello | bob: hello",
    "<@U1> (Alice): hello | <@U2> (Bob): hello",
    "[123] [1] @alice: hi\n[123] [2] @bob: hi"])
def test_multiple_senders(policy, text):
    assert router_policy.needs_premium(request(text), None)


def test_routine_for_same_sender_and_system_keywords_are_ignored(policy):
    req = request("alice: hello", "alice: what time is it?")
    req.messages.insert(0, SimpleNamespace(role="system", content="premium deep_reasoning"))
    assert not router_policy.needs_premium(req, None)


def test_previous_failure_escalates(policy):
    assert router_policy.needs_premium(request("hello"), {"failed": True})


@pytest.mark.parametrize("router", ["default", "none"])
def test_independent_instances_and_routine_default(monkeypatch, router):
    class FakeProvider(providers.LLMProvider):
        def start(self):
            self.delegate = SimpleNamespace(_model_name=config.config_get_by_key("model"))
            self.route = config.config_get_by_key("provider_gateway_route")

        def chat(self, req):
            self.request = req
            return providers.LLMResponse().with_error("test response")

    monkeypatch.setattr(providers, "_role_providers", {})
    monkeypatch.setattr(providers, "_catalogue", {})
    monkeypatch.setattr(providers, "_llmprovider", None)
    monkeypatch.setattr(providers, "_last_outcome", None)
    monkeypatch.setattr(config, "_CONFIG", {})
    monkeypatch.setattr(config, "_CONFIG_FILE", {})
    monkeypatch.setattr(config, "_COMMAND_LINE", {
        "router": router,
        "router_catalog": {"routine": record("small"), "premium": record("large")}})
    monkeypatch.setattr(providers, "_router", router)
    monkeypatch.setattr(providers, "_llmProviderRegistry", {"OpenAI": FakeProvider()})
    providers.llmProviderStart("OpenAI")
    routine = providers._role_providers["routine"]
    if router == "none":
        assert list(providers._role_providers) == ["routine"]
        assert [entry["model_name"] for entry in providers.llmCatalogueGet()] == ["routine"]
        assert providers.llmRouterStart() == "none"
        req = providers.LLMRequest()
        providers.llmProviderChat(req)
        assert routine.request is req
        assert req.model == "small"
        return
    premium = providers._role_providers["premium"]
    assert routine is not premium
    assert (routine.delegate._model_name, premium.delegate._model_name) == ("small", "large")
    assert (routine.route, premium.route) == ("catalog/routine", "catalog/premium")
    req = providers.LLMRequest()
    providers.llmProviderChat(req)
    assert routine.request is req
    assert req.model == "small"
    selection = router_policy.catalog_selection(providers.llmCatalogueGet(), "premium")
    assert selection == {"provider": "OpenAI", "model": "large", "role": "premium"}
    providers.llmProviderChatRouted(req, selection)
    assert premium.request is req
    assert req.model == "large"


def test_router_returns_provider_and_model_from_catalog():
    catalog = [
        {"model_name": "routine", "provider": "OpenAI", "model": "small"},
        {"model_name": "premium", "provider": "Anthropic", "model": "large"},
    ]
    assert router_policy.catalog_selection(catalog, "premium") == {
        "provider": "Anthropic", "model": "large", "role": "premium"}
    with pytest.raises(ValueError):
        router_policy.catalog_selection(catalog, "missing")


@pytest.mark.parametrize("selection", ["routine", ("Missing", "small"),
    {"provider": "OpenAI", "model": "unknown"},
    {"provider": "OpenAI", "model": "small", "role": "premium"}])
def test_invalid_router_selections_make_no_provider_call(monkeypatch, selection):
    monkeypatch.setattr(providers, "_catalogue", {
        "routine": {"provider": "OpenAI", "model": "small"}})
    monkeypatch.setattr(providers, "_role_providers", {})
    monkeypatch.setattr(providers, "_last_outcome", None)
    assert providers.llmProviderChatRouted(providers.LLMRequest(), selection).is_error()


def test_duplicate_provider_model_requires_role_metadata(monkeypatch):
    monkeypatch.setattr(providers, "_catalogue", {
        "routine": {"provider": "OpenAI", "model": "same"},
        "premium": {"provider": "OpenAI", "model": "same"}})
    monkeypatch.setattr(providers, "_last_outcome", None)
    dispatched = []
    monkeypatch.setattr(providers, "_llmProviderChatRecord",
                        lambda req, role, provider, model: dispatched.append((role, provider, model)))
    req = providers.LLMRequest()
    assert providers.llmProviderChatRouted(req, ["OpenAI", "same"]).is_error()
    assert dispatched == []
    providers.llmProviderChatRouted(req, {"provider": "OpenAI", "model": "same", "role": "premium"})
    assert dispatched == [("premium", "OpenAI", "same")]


def test_explicit_provider_model_pair_dispatches(monkeypatch):
    monkeypatch.setattr(providers, "_catalogue", {
        "premium": {"provider": "Anthropic", "model": "large"}})
    dispatched = []
    monkeypatch.setattr(providers, "_llmProviderChatRecord",
                        lambda req, role, provider, model: dispatched.append((role, provider, model)))
    providers.llmProviderChatRouted(providers.LLMRequest(), ["Anthropic", "large"])
    assert dispatched == [("premium", "Anthropic", "large")]


def test_single_record_disables_router(monkeypatch):
    monkeypatch.setattr(providers, "_catalogue", {"routine": {}})
    monkeypatch.setattr(providers, "_router", "default")
    monkeypatch.setattr(config, "config_get_by_key", lambda key, default=None: "default")
    assert providers.llmRouterStart() == "none"
    assert not providers.llmRoutingEnabled()
