"""The envelope carries the provider and the model; every provider honours it
(R3, OMEGA-376 increment 1, ADR-0001).

Provider plugins are loaded the way src/plugin.py:loadPythonPlugin loads them,
as in test_lib_llm_ext.py. Dummy keys, no network, no client constructed: the
chat tests hand each provider a stub client.
"""
import ast
import importlib
import importlib.util
import logging
import pathlib
import sys
import types

import pytest

import config
import providers
from providers import *

REPO = pathlib.Path(__file__).resolve().parent.parent
PROVIDERS = REPO / "providers"
# convert_request output of each provider for _baseline_request(), generated on
# c193ab3 (#358 as #373 merged it: the A1 baseline, spec B17); the file names how.
SNAPSHOT = REPO / "tests" / "res" / "providers" / "convert_request@c193ab3.py"

CONFIGURED = {
    "openaiapi": "qwen3.5:9b",
    "asione": "asi1-ultra",
    "openrouter": "z-ai/glm-5.2",
    "openai": "gpt-5.5",
}


@pytest.fixture
def plugins(monkeypatch):
    logger_mod = types.ModuleType("src.logger")
    logger_mod.get_logger = lambda name: logging.getLogger(name)
    monkeypatch.setitem(sys.modules, "src.logger", logger_mod)
    # tests/pytest.sh runs on the CI host, where requirements.txt is not installed;
    # with providers/ on sys.path, `import openai` would load providers/openai.py.
    # No test here constructs a client, so a stand-in package is enough.
    openai_mod = types.ModuleType("openai")
    openai_mod.OpenAI = object
    monkeypatch.setitem(sys.modules, "openai", openai_mod)
    monkeypatch.setattr(sys, "path", sys.path + [str(PROVIDERS)])
    # Every configuration key resolves to its default, whatever the environment holds.
    monkeypatch.setattr(config, "_CONFIG", {})
    monkeypatch.setattr(config, "_COMMAND_LINE", {})
    monkeypatch.setattr(config, "_CONFIG_FILE", {})
    for key in ("OPENAI_PROMPT_CACHE_KEY", "OPENROUTER_SESSION_ID", "OPENROUTER_CACHE_TTL"):
        monkeypatch.delenv(f"OMEGA_{key}", raising=False)

    def load(name):
        spec = importlib.util.spec_from_file_location(f"omega_plugin_{name}", PROVIDERS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load


def _ai_providers(load, monkeypatch, models=CONFIGURED):
    """The four AIProvider implementations, built as their plugins build them."""
    for var in ("OPENAIAPI_API_KEY", "ASIONE_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(var, "dummy-key")
    llm = importlib.import_module("lib_llm_ext")  # as the provider plugins import it
    return {
        "openaiapi": llm.AIProvider("OpenAIAPI", "OPENAIAPI_API_KEY", models["openaiapi"], "http://localhost:11434/v1/"),
        "asione": load("asione").ASIOneProviderImpl("ASIOne", "ASIONE_API_KEY", models["asione"], "https://api.asi1.ai/v1"),
        "openrouter": load("openrouter").OpenRouterProviderImpl("OpenRouter", "OPENROUTER_API_KEY", models["openrouter"], "https://openrouter.ai/api/v1"),
        "openai": load("openai").OpenAIProviderImpl("OpenAI", "OPENAI_API_KEY", models["openai"], "https://api.openai.com/v1"),
    }


def _baseline_request(system="You are Omega. HISTORY: none yet"):
    """A fixed request built with the API c193ab3 already has, so the
    snapshot can be generated there."""
    send = LLMTool().with_name("send").with_description("Send a message").add_parameter(LLMToolParameter().with_name("content"))
    call = LLMToolCall().with_name("send").with_id("call_1").with_arguments({"content": "hello"})
    return (LLMRequest().with_messages([llmRequestMessage("system", system),
                                        llmRequestMessage("user", "hi"),
                                        llmToolCallMessage("assistant", [call], ""),
                                        llmToolCallResponseMessage("tool", "call_1", "sent")])
                        .with_max_tokens(1000)
                        .with_reasoning_mode("medium")
                        .with_tools([send]))


def test_request_built_todays_way_has_an_empty_envelope():
    """R3-FR1: provider, model, router and metadata default to empty."""
    request = llmRequest(llmRequestMessage("system", "prompt"), [], 100, "medium", [])
    assert (request.provider, request.model, request.router, request.metadata) == ("", "", "", {})


def test_set_model_reaches_the_raw_request(plugins, monkeypatch):
    """R3-T1 (A8): every real provider sends the model the envelope names."""
    for name, provider in _ai_providers(plugins, monkeypatch).items():
        raw = provider.convert_request(_baseline_request().with_model("routed-x"))
        assert raw["model"] == "routed-x", name


def test_unset_model_keeps_the_baseline_raw_request(plugins, monkeypatch):
    """R3-T2 (A1): with no model named, the configured model is sent and the
    whole raw request equals the one c193ab3 builds."""
    snapshot = ast.literal_eval(SNAPSHOT.read_text())
    assert set(snapshot) == set(CONFIGURED)
    for name, provider in _ai_providers(plugins, monkeypatch).items():
        raw = provider.convert_request(_baseline_request())
        assert raw["model"] == CONFIGURED[name], name
        assert raw == snapshot[name], name


def test_openai_retention_follows_the_effective_model(plugins, monkeypatch):
    """R3-T3: the gpt-5.5/gpt-5.4 retention branch reads the routed model."""
    openai = _ai_providers(plugins, monkeypatch, {**CONFIGURED, "openai": "gpt-4.1"})["openai"]
    assert openai.convert_request(_baseline_request().with_model("gpt-5.5-mini"))["prompt_cache_retention"] == "24h"
    openai = _ai_providers(plugins, monkeypatch, {**CONFIGURED, "openai": "gpt-5.5"})["openai"]
    assert "prompt_cache_retention" not in openai.convert_request(_baseline_request().with_model("gpt-4.1"))


def test_openai_cache_key_follows_the_effective_model(plugins, monkeypatch):
    """R3-T4: same system message, different model -> different prompt_cache_key."""
    openai = _ai_providers(plugins, monkeypatch)["openai"]
    key = lambda model: openai.convert_request(_baseline_request().with_model(model))["prompt_cache_key"]
    assert key("model-a") != key("model-b")
    assert key("model-a") == key("model-a")


def test_openrouter_cache_control_follows_the_effective_model(plugins, monkeypatch):
    """R3-T5 (FR3): is_anthropic and _stable_cache_key read the routed model."""
    openrouter = _ai_providers(plugins, monkeypatch, {**CONFIGURED, "openrouter": "z-ai/glm-5.2"})["openrouter"]
    body = openrouter.convert_request(_baseline_request().with_model("anthropic/claude-x"))["extra_body"]
    assert "cache_control" in body
    assert body["session_id"].startswith("openrouter:anthropic/claude-x:")
    openrouter = _ai_providers(plugins, monkeypatch, {**CONFIGURED, "openrouter": "anthropic/claude-x"})["openrouter"]
    body = openrouter.convert_request(_baseline_request().with_model("z-ai/glm-5.2"))["extra_body"]
    assert "cache_control" not in body
    assert body["session_id"].startswith("openrouter:z-ai/glm-5.2:")


def test_repr_prints_the_routing_fields():
    """R3-T6 (A9, FR4): the REQUEST: log line shows provider, model and router,
    in the class's own name=repr(value) convention, and no metadata value."""
    request = (LLMRequest().with_provider("p").with_model("m").with_router("r")
                           .with_metadata({"note": "user text"}))
    printed = repr(request)
    for name, value in (("provider", "p"), ("model", "m"), ("router", "r")):
        assert f"{name}={value!r}" in printed
    assert "user text" not in printed


def _raw_response():
    """Enough of a Chat Completions and a Responses result for convert_response."""
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(finish_reason="stop", message=types.SimpleNamespace(tool_calls=[]))],
        output=[], usage=None, status="completed", incomplete_details=None)


class _StubClient:
    def __init__(self):
        create = lambda **raw_request: _raw_response()
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
        self.responses = types.SimpleNamespace(create=create)


def test_log_lines_name_the_effective_model(plugins, monkeypatch, caplog):
    """R3-T7 (FR2): LLM_RAW_REQUEST, LLM_RAW_RESPONSE and LLM_USAGE name the routed model."""
    caplog.set_level(logging.DEBUG)
    for name, provider in _ai_providers(plugins, monkeypatch).items():
        caplog.clear()
        provider._client = _StubClient()
        provider.chat(_baseline_request().with_model("routed-x"))
        lines = [record.getMessage() for record in caplog.records if " provider=" in record.getMessage()]
        assert {line.split(" ", 1)[0] for line in lines} >= {"[LLM_RAW_REQUEST]", "[LLM_RAW_RESPONSE]", "[LLM_USAGE]"}, name
        for line in lines:
            assert " model=routed-x " in line, (name, line[:120])


def test_envelope_provider_selects_nothing(monkeypatch):
    """R3-FR5: request.provider does not change which provider instance is called."""
    called = []

    class _Recorder(LLMProvider):
        def __init__(self, id):
            self.id = id

        def chat(self, request):
            called.append(self.id)
            return LLMResponse()

    monkeypatch.setattr(providers, "_llmProviderRegistry", {"A": _Recorder("A"), "B": _Recorder("B")})
    monkeypatch.setattr(providers, "_llmprovider", None)
    providers.llmProviderStart("A")
    providers.llmProviderChat(LLMRequest().with_provider("B"))
    assert called == ["A"]


# LLMProvider.model() (spec section 14a B4): the model a provider calls when the
# request names none, asked once after llmProviderStart to build the catalogue.

def _wrappers(load):
    """The registered provider objects, as their plugins construct them."""
    openaiapi = load("openaiapi")
    return {
        "OpenAI": (load("openai").OpenAIProvider(), "openai_model", "gpt-5.5"),
        "OpenRouter": (load("openrouter").OpenRouterProvider(), "openrouter_model", "z-ai/glm-5.2"),
        "ASIOne": (load("asione").ASIOneProvider(), "asione_model", "asi1-ultra"),
        "OpenAIAPI": (openaiapi.OpenAIAPI("OpenAIAPI"), "openaiapi_model", "qwen3.5:9b"),
        "Anthropic": (openaiapi.OpenAIAPIPreconfigured("Anthropic", "ANTHROPIC_API_KEY", "claude-opus-4-8",
                                                       "https://api.anthropic.com/v1/"), None, "claude-opus-4-8"),
    }


@pytest.mark.parametrize("name", ["OpenAI", "OpenRouter", "ASIOne", "OpenAIAPI", "Anthropic"])
def test_provider_reports_its_plugin_default_model(plugins, name):
    provider, _, default = _wrappers(plugins)[name]
    provider.start()
    assert provider.model() == default


@pytest.mark.parametrize("name", ["OpenAI", "OpenRouter", "ASIOne", "OpenAIAPI"])
def test_provider_reports_its_own_model_key(plugins, monkeypatch, name):
    """Its own *_model key, never another provider's (R5-T1's concern at the source)."""
    wrappers = _wrappers(plugins)
    provider, key, _ = wrappers[name]
    others = {other: "other-1" for _, other, _ in wrappers.values() if other and other != key}
    monkeypatch.setattr(config, "_CONFIG_FILE", {key: "own-1", **others})
    provider.start()
    assert provider.model() == "own-1"


@pytest.mark.parametrize("name", ["OpenAI", "OpenRouter", "ASIOne", "OpenAIAPI", "Anthropic"])
def test_model_key_overrides_the_provider_model(plugins, monkeypatch, name):
    provider, key, _ = _wrappers(plugins)[name]
    monkeypatch.setattr(config, "_CONFIG_FILE", {"model": "econ-1", **({key: "own-1"} if key else {})})
    provider.start()
    assert provider.model() == "econ-1"


def test_test_provider_reports_the_model_key_or_nothing(plugins, monkeypatch):
    """The Test mock has no model concept: model() is the model key, else ""."""
    mock = plugins("mockprovider").MockProvider()
    assert mock.model() == ""
    monkeypatch.setattr(config, "_CONFIG", {})
    monkeypatch.setattr(config, "_CONFIG_FILE", {"model": "econ-1"})
    assert mock.model() == "econ-1"
