"""The catalogue: an allow-list of (provider, model), enumerated at startup
(R5, OMEGA-376 increment 1, ADR-0001).

In increment 1 the catalogue is the running provider's configured model plus
premium_model, both on the running provider (spec section 4, invariant 3; O4).
A value outside it is refused before any provider is called (A5).
"""
import pytest

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


def test_check_refuses_an_empty_model_even_if_the_catalogue_holds_one():
    """An empty model is malformed, never "the configured one" (no silent fallback)."""
    assert llmCatalogueRefusal([("Test", "")], ("Test", "")) is not None
