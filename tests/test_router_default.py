"""The default router's configuration (R7, OMEGA-376 increment 1, ADR-0001).

The policy itself is MeTTa and is tested in tests/router_default.metta. Here:
the keywords are normalised with the request text's own function (O7, R7-T3),
and the documented defaults are the ones the router resolves (A4c, R7-T5).
"""
import logging
import pathlib
import re

import pytest

from providers import *

REPO = pathlib.Path(__file__).resolve().parent.parent


# R7-T3, R7-FR2 (O7)

def test_keywords_are_normalised_like_the_text(caplog):
    caplog.set_level(logging.INFO)
    assert llmKeywordsNormalized("Premium_Model") == ["premium_model"]
    assert llmKeywordsNormalized("alert_failed, Error.,premium_model") == ["alert_failed", "error", "premium_model"]
    assert any("['alert_failed', 'error', 'premium_model']" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("keyword", ["a b", "()", ""])
def test_a_keyword_that_cannot_match_fails_startup_naming_it(caplog, keyword):
    with pytest.raises(RuntimeError) as error:
        llmKeywordsNormalized(f"error,{keyword}")
    assert repr(keyword) in str(error.value)
    assert str(error.value) in [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]


# R7-T5, R7-FR4 (spec section 10): one source for the defaults

def _documented(key):
    match = re.search(rf"^#{key}: (.+)$", (REPO / "config" / "config.yaml").read_text(), re.M)
    assert match, f"config/config.yaml documents no {key}"
    return match.group(1).strip()


def _router_default(form, key):
    text = (REPO / "routers" / "default.metta").read_text()
    match = re.search(rf"\({form} {key} (\S+?)\)", text)
    assert match, f"routers/default.metta has no ({form} {key} ...) default"
    return match.group(1)


def test_the_documented_defaults_are_the_ones_the_router_resolves():
    keywords = _documented("router_escalate_keywords")
    assert keywords == _router_default("configGetByKey", "router_escalate_keywords")
    assert _documented("router_escalate_items") == _router_default("configure", "router_escalate_items")
    # the intent's keywords (spec section 14, Q1) and #373's threshold (section 10)
    assert llmKeywordsNormalized(keywords.strip('"')) == ["alert_failed", "error", "premium_model"]
    assert _documented("router_escalate_items") == "9"


@pytest.mark.parametrize("path", ["routers/README.md", "scripts/omega"])
def test_nothing_else_names_other_keywords(path):
    documented = _documented("router_escalate_keywords")
    for named in re.findall(r"router_escalate_keywords\W+(\"[^\"]*\")", (REPO / path).read_text()):
        assert named == documented, f"{path} names {named}, config/config.yaml documents {documented}"
