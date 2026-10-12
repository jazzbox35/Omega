"""The catalogue: an allow-list of (provider, model), enumerated at startup
(R5, OMEGA-376 increment 1, ADR-0001).

In increment 1 the catalogue is the running provider's configured model plus
premium_model, both on the running provider (spec section 4, invariant 3; O4).
A value outside it is refused before any provider is called (A5).
"""
import logging

import pytest

import config
import providers
from providers import *


def test_catalogue_is_the_running_provider_with_model_and_premium_model():
    """R5-T1 (FR1): model and premium_model on the running provider, nothing else."""
    assert llmCatalogue("Test", "econ-1", "prem-1", "default") == [("Test", "econ-1"), ("Test", "prem-1")]


def test_catalogue_without_premium_model_or_router_is_the_configured_model():
    """R5-T1 (FR1): no premium_model and no router -> one entry."""
    assert llmCatalogue("Test", "econ-1", "", "") == [("Test", "econ-1")]


def test_catalogue_is_built_from_values_not_from_other_providers_keys():
    """R5-T1 (FR1): another provider's *_model key cannot enter the catalogue,
    because the builder is given the running provider's values only."""
    catalogue = llmCatalogue("Test", "econ-1", "prem-1", "default")
    assert all(provider == "Test" for provider, _ in catalogue)
    assert len(catalogue) == 2


def test_premium_model_equal_to_model_is_one_entry():
    assert llmCatalogue("Test", "econ-1", "econ-1", "default") == [("Test", "econ-1")]


def test_router_without_premium_model_fails_naming_the_key():
    """R5-FR4 (spec section 3, O4.4): router configured, premium_model unset -> startup fails."""
    with pytest.raises(RuntimeError) as error:
        llmCatalogue("Test", "econ-1", "", "default")
    assert "premium_model" in str(error.value)
    assert "default" in str(error.value)


CATALOGUE = [("Test", "econ-1"), ("Test", "prem-1")]


@pytest.mark.parametrize("value", [("Test", "econ-1"), ("Test", "prem-1"), ["Test", "prem-1"]])
def test_check_permits_a_pair_in_the_catalogue(value):
    """R5-T2: permitted pairs pass."""
    assert llmCatalogueRefusal(CATALOGUE, value) is None


@pytest.mark.parametrize("value", [
    ("Test", "not-permitted"),            # out of catalogue
    ("Other", "econ-1"),                  # another provider (A5)
    ("", ""),                             # empty
    None,                                 # not a pair
    ("Test", "econ-1", "extra"),          # a 3-tuple
    ("Test", None),                       # not a string
    "Test econ-1",                        # a string, not a pair
])
def test_check_refuses_naming_the_value_and_the_catalogue(value):
    """R5-T2 (FR3, spec section 3): refused; the line names the rejected value
    as received, and the catalogue."""
    refusal = llmCatalogueRefusal(CATALOGUE, value)
    assert refusal is not None
    assert repr(value) in refusal
    assert repr(CATALOGUE) in refusal


def test_check_compares_an_empty_model_as_a_value():
    """Spec section 14a B4: "" is a model only for a provider with no model
    concept (Test without model set). The check compares it as any value: in
    the catalogue it passes, so a no-router Test run behaves as today;
    otherwise it is refused like any other pair."""
    assert llmCatalogueRefusal([("Test", "")], ("Test", "")) is None
    assert llmCatalogueRefusal(CATALOGUE, ("Test", "")) is not None


class _Fake(LLMProvider):
    """A registered provider with no model concept of its own: model() is the base's."""
    started = False

    def start(self):
        self.started = True


@pytest.fixture
def start(monkeypatch, caplog):
    """llmProviderStart("Fake") under a clean configuration made of `values`."""
    for key in ("model", "premium_model", "router"):
        monkeypatch.delenv(f"OMEGA_{key}", raising=False)
    monkeypatch.setattr(config, "_COMMAND_LINE", {})
    monkeypatch.setattr(providers, "_llmprovider", None)
    monkeypatch.setattr(providers, "_catalogue", None)
    caplog.set_level(logging.INFO)

    def run(**values):
        monkeypatch.setattr(config, "_CONFIG", {})
        monkeypatch.setattr(config, "_CONFIG_FILE", values)
        fake = _Fake()
        monkeypatch.setitem(providers._llmProviderRegistry, "Fake", fake)
        providers.llmProviderStart("Fake")
        return fake
    return run


def _catalogue_lines(caplog):
    return [r.getMessage() for r in caplog.records if "catalogue" in r.getMessage()]


def test_startup_builds_and_logs_the_catalogue_once(start, caplog):
    """R5-FR1, FR2 (B4): built once after start() from model(), logged in full."""
    fake = start(model="econ-1", premium_model="prem-1", router="default")
    assert fake.started
    assert providers._catalogue == [("Fake", "econ-1"), ("Fake", "prem-1")]
    lines = _catalogue_lines(caplog)
    assert len(lines) == 1
    assert repr(providers._catalogue) in lines[0]


@pytest.mark.parametrize("router", [None, "no_router"])
def test_startup_without_a_router_needs_no_premium_model(start, router):
    """Off (unset, or loop.metta's no_router until R6) starts with one entry."""
    start(**({"model": "econ-1"} if router is None else {"model": "econ-1", "router": router}))
    assert providers._catalogue == [("Fake", "econ-1")]


def test_startup_of_a_provider_with_no_model_holds_the_empty_model(start):
    """B4: Test without model set; "" is compared as a value later."""
    start()
    assert providers._catalogue == [("Fake", "")]


def test_startup_with_a_router_and_no_premium_model_fails(start):
    """R5-FR4 (spec section 3, O4.4): startup fails, naming the key."""
    with pytest.raises(RuntimeError) as error:
        start(model="econ-1", router="default")
    assert "premium_model" in str(error.value)
    assert providers._catalogue is None
