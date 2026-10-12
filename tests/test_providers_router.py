"""The router registry, the null router and the hook (R6, OMEGA-376 increment 1,
ADR-0001).

A router is a MeTTa function registered by name from a plugin (routers/,
config/plugins.yaml). Core keeps the names, resolves the configured one once
at startup, and runs the null router when none is configured: one code path.
The hook calls the router for every request, completes only the envelope's
empty fields from its (provider, model) answer, and checks the result against
the catalogue before the provider is entered.
"""
import importlib.util
import logging
import pathlib
import sys
import types

import pytest

import config
import providers
from providers import *

PROVIDERS = pathlib.Path(__file__).resolve().parent.parent / "providers"


@pytest.fixture
def clean(monkeypatch, caplog):
    for key in ("model", "premium_model", "router"):
        monkeypatch.delenv(f"OMEGA_{key}", raising=False)
    monkeypatch.setattr(config, "_COMMAND_LINE", {})
    monkeypatch.setattr(config, "_CONFIG", {})
    monkeypatch.setattr(config, "_CONFIG_FILE", {})
    monkeypatch.setattr(providers, "_llmProviderRegistry", {})
    monkeypatch.setattr(providers, "_llmRouterRegistry", [])
    monkeypatch.setattr(providers, "_llmprovider", None)
    monkeypatch.setattr(providers, "_catalogue", None)
    caplog.set_level(logging.INFO)
    return monkeypatch


def _lines(caplog, level=None):
    return [r.getMessage() for r in caplog.records if level is None or r.levelno == level]


# The registry (R6-FR1, FR3, FR5)

def test_routers_register_by_name(clean, caplog):
    assert registerLLMRouter("a") == "a"
    assert registerLLMRouter("b") == "b"
    assert providers._llmRouterRegistry == ["a", "b"]
    assert any("registerLLMRouter" in line and "a" in line for line in _lines(caplog))


def test_the_null_router_registers_under_the_empty_name_unlisted(clean):
    """src/providers.metta registers the null router under "", the name no
    configuration gives; it is not one of the routers a halt lists."""
    assert registerLLMRouter("") == ""
    assert providers._llmRouterRegistry == []


@pytest.mark.parametrize("router", [None, ""])
def test_start_without_a_router_runs_the_null_router(clean, caplog, router):
    """R6-FR2, FR5: no router configured starts normally; the log names null."""
    registerLLMRouter("a")
    assert llmRouterStart(router) == ""
    assert "llmRouterStart: router null" in _lines(caplog, logging.INFO)


def test_start_names_the_configured_router(clean, caplog):
    """R6-FR5."""
    registerLLMRouter("a")
    registerLLMRouter("b")
    assert llmRouterStart("b") == "b"
    assert "llmRouterStart: router b" in _lines(caplog, logging.INFO)


class _Symbol:
    """Stands in for a value configure may hand over as other than a str."""
    def __str__(self):
        return "a"


def test_start_reads_the_name_through_str(clean):
    registerLLMRouter("a")
    assert llmRouterStart(_Symbol()) == "a"


def test_an_unknown_router_halts_naming_it_and_the_registered(clean, caplog):
    """R6-FR3, A6 (O6.1): startup fails, naming the unknown router and the
    registered ones."""
    registerLLMRouter("default")
    registerLLMRouter("qa_fixed")
    with pytest.raises(RuntimeError) as error:
        llmRouterStart("defualt")
    for name in ("defualt", "default", "qa_fixed"):
        assert name in str(error.value)
    assert str(error.value) in _lines(caplog, logging.ERROR)


def test_off_and_unknown_never_share_a_line(clean, caplog):
    """R6-FR3: "off" starts and logs null; "unknown" halts with its own line."""
    registerLLMRouter("a")
    llmRouterStart("")
    off = _lines(caplog)
    caplog.clear()
    with pytest.raises(RuntimeError):
        llmRouterStart("b")
    unknown = _lines(caplog)
    assert not set(off) & set(unknown)


# The null router and the hook

class _Recorder(LLMProvider):
    """A running provider that records what reaches it."""

    def __init__(self):
        self.requests = []

    def chat(self, request):
        self.requests.append((request.provider, request.model))
        return LLMResponse()


@pytest.fixture
def running(clean):
    """Provider "Fake" started with model econ-1 and premium_model prem-1."""
    clean.setattr(config, "_CONFIG_FILE", {"model": "econ-1", "premium_model": "prem-1"})
    fake = _Recorder()
    providers._llmProviderRegistry["Fake"] = fake
    llmProviderStart("Fake")
    return fake


def test_null_router_completes_an_empty_envelope_from_configuration(running):
    """R6-T2: empty model -> the configured model, on the running provider."""
    assert list(llmNullRouter(LLMRequest())) == ["Fake", "econ-1"]


def test_null_router_keeps_what_the_envelope_names(running):
    """R6-T2, R6-FR4 (invariant 8): a named field comes back unchanged."""
    assert list(llmNullRouter(LLMRequest().with_model("x"))) == ["Fake", "x"]
    assert list(llmNullRouter(LLMRequest().with_provider("P"))) == ["P", "econ-1"]


def test_null_router_answer_reaches_the_provider(running):
    """R6-FR2: routing off is the null router through the hook, one path."""
    request = LLMRequest()
    llmProviderChatRouted(request, "", llmNullRouter(request))
    assert running.requests == [("Fake", "econ-1")]


def test_a_permitted_answer_completes_the_envelope_and_reaches_the_provider(running):
    llmProviderChatRouted(LLMRequest(), "r", ["Fake", "prem-1"])
    assert running.requests == [("Fake", "prem-1")]


def test_a_model_the_agent_named_is_kept_whatever_the_router_answers(running):
    """R6-FR4, invariant 8 (O6.3): the router fills only empty fields."""
    llmProviderChatRouted(LLMRequest().with_model("econ-1"), "r", ["Fake", "prem-1"])
    assert running.requests == [("Fake", "econ-1")]


def test_a_model_the_agent_named_is_still_checked(running, caplog):
    """Invariant 8: kept, and still checked against the catalogue (FR5 of R5)."""
    response = llmProviderChatRouted(LLMRequest().with_model("x"), "r", ["Fake", "prem-1"])
    assert running.requests == []
    assert response == LLMResponse()
    assert any("'x'" in line for line in _lines(caplog, logging.ERROR))


@pytest.mark.parametrize("answer", [
    ["Fake", "not-permitted"],       # outside the catalogue
    ["OtherProvider", "econ-1"],     # another provider (A5)
    "prem-1",                        # malformed: not a pair
    ["Fake"],                        # malformed: one element
    ["Fake", 1],                     # malformed: not a string
    None,                            # malformed: nothing
])
def test_a_refused_answer_never_reaches_the_provider(running, caplog, answer):
    """A5, R5-FR3/T3 (spec section 3): zero provider calls, an empty response,
    and one ERROR line naming the router, the value received and the catalogue."""
    response = llmProviderChatRouted(LLMRequest(), "qa_fixed", answer)
    assert running.requests == []
    assert response == LLMResponse()
    errors = _lines(caplog, logging.ERROR)
    assert len(errors) == 1
    assert "qa_fixed" in errors[0]
    assert repr(providers._catalogue) in errors[0]
    shown = answer if not isinstance(answer, list) or len(answer) != 2 else tuple(answer)
    assert repr(shown) in errors[0]


def test_a_raising_router_is_refused_naming_it_and_the_exception(running, caplog):
    """Spec section 3, O6.2: refused, zero calls, the exception and the
    router's name logged; never a fallback to the null router."""
    response = llmRouterRaised("qa_fixed", "(Error (qa_fixed) boom)")
    assert running.requests == []
    assert response == LLMResponse()
    errors = _lines(caplog, logging.ERROR)
    assert len(errors) == 1
    assert "qa_fixed" in errors[0] and "boom" in errors[0]


def test_the_next_request_after_a_refusal_is_answered(running):
    """Gherkin: "the agent answers the next message normally"."""
    llmProviderChatRouted(LLMRequest(), "qa_fixed", ["Fake", "not-permitted"])
    llmRouterRaised("qa_fixed", "boom")
    llmProviderChatRouted(LLMRequest(), "qa_fixed", ["Fake", "prem-1"])
    assert running.requests == [("Fake", "prem-1")]


def test_test_with_no_model_key_is_answered_through_the_hook(clean, monkeypatch):
    """QA 4d88a559 (b), at R6's head: the mock Test, no model key, no router.
    The null router's ("Test", "") is in the catalogue {(Test, "")}, so the
    request reaches the provider and is answered, as at c193ab3."""
    logger_mod = types.ModuleType("src.logger")
    logger_mod.get_logger = lambda name: logging.getLogger(name)
    monkeypatch.setitem(sys.modules, "src.logger", logger_mod)
    monkeypatch.setattr(sys, "path", sys.path + [str(PROVIDERS)])
    spec = importlib.util.spec_from_file_location("omega_plugin_mockprovider", PROVIDERS / "mockprovider.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.loadOmegaPlugin()
    llmProviderStart("Test")
    llmRouterStart("")
    answered = LLMResponse().with_error(None)
    reached = []
    mock = providers._llmProviderRegistry["Test"]
    monkeypatch.setattr(mock.delegate, "chat", lambda request: reached.append(request.model) or answered)
    request = LLMRequest()
    assert llmProviderChatRouted(request, "", llmNullRouter(request)) is answered
    assert reached == [""]
