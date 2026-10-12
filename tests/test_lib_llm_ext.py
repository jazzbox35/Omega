"""AIProvider client lifecycle (R1, OMEGA-376 increment 1).

Provider plugins are loaded the way src/plugin.py:loadPythonPlugin loads them:
by file location, with the providers folder appended (never prepended) to
sys.path, and without registering the module in sys.modules, so that
providers/openai.py does not shadow the openai package.
"""
import ast
import importlib
import importlib.util
import pathlib
import sys
import types

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
PROVIDERS = REPO / "providers"


@pytest.fixture
def plugins(monkeypatch):
    logger_mod = types.ModuleType("src.logger")
    logger_mod.get_logger = lambda name: __import__("logging").getLogger(name)
    monkeypatch.setitem(sys.modules, "src.logger", logger_mod)
    # tests/pytest.sh runs on the CI host, where requirements.txt is not installed;
    # with providers/ on sys.path, `import openai` would load providers/openai.py.
    # No test here constructs a client, so a stand-in package is enough.
    openai_mod = types.ModuleType("openai")
    openai_mod.OpenAI = object
    monkeypatch.setitem(sys.modules, "openai", openai_mod)
    monkeypatch.setattr(sys, "path", sys.path + [str(PROVIDERS)])

    def load(name):
        spec = importlib.util.spec_from_file_location(f"omega_plugin_{name}", PROVIDERS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load


def _ai_providers(load, monkeypatch):
    """The four AIProvider implementations, built as their plugins build them.
    MockProviderImpl is not an AIProvider and guards its own stop()."""
    for var in ("OPENAIAPI_API_KEY", "ASIONE_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(var, "dummy-key")
    llm = importlib.import_module("lib_llm_ext")  # as the provider plugins import it
    return {
        "openaiapi": llm.AIProvider("OpenAIAPI", "OPENAIAPI_API_KEY", "qwen3.5:9b", "http://localhost:11434/v1/"),
        "asione": load("asione").ASIOneProviderImpl("ASIOne", "ASIONE_API_KEY", "asi1-ultra", "https://api.asi1.ai/v1"),
        "openrouter": load("openrouter").OpenRouterProviderImpl("OpenRouter", "OPENROUTER_API_KEY", "z-ai/glm-5.2", "https://openrouter.ai/api/v1"),
        "openai": load("openai").OpenAIProviderImpl("OpenAI", "OPENAI_API_KEY", "gpt-5.5", "https://api.openai.com/v1"),
    }


class _CountingClient:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


def test_stop_without_a_call_does_not_raise(plugins, monkeypatch):
    """R1-T1: stopping a provider that never made a call returns normally."""
    for name, provider in _ai_providers(plugins, monkeypatch).items():
        provider.stop()
        assert provider._client is None, name


def test_stop_closes_the_client_once(plugins, monkeypatch):
    """R1-T2: stop() after a call closes the client once; a second stop() is a no-op."""
    for name, provider in _ai_providers(plugins, monkeypatch).items():
        client = _CountingClient()
        provider._client = client
        provider.stop()
        provider.stop()
        assert client.closed == 1, name
        assert provider._client is None, name


def _client_reaches(providers):
    """Locations outside lib_llm_ext.py that read `_client` on an object other
    than `self`: an attribute read, or getattr(<x>, "_client")."""
    reaches = []
    for path in sorted(providers.glob("*.py")):
        if path.name == "lib_llm_ext.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            if isinstance(node, ast.Attribute) and node.attr == "_client":
                receiver = node.value
            elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "getattr" and len(node.args) >= 2 \
                    and isinstance(node.args[1], ast.Constant) and node.args[1].value == "_client":
                receiver = node.args[0]
            else:
                continue
            if not (isinstance(receiver, ast.Name) and receiver.id == "self"):
                reaches.append(f"{path.name}:{node.lineno}")
    return reaches


def test_no_provider_reaches_into_another_objects_client(tmp_path):
    """R1-T3 (QA addendum 1): outside lib_llm_ext.py, no code reads `_client` on
    an object other than `self` (the private reach PR #373 added in
    OpenRouterProvider.stop). A subclass may use its own `self._client`
    (OpenAIProviderImpl.chat). Aliasing is not followed (`c = self; c.delegate`)."""
    fixtures = REPO / "tests" / "res" / "architecture"
    assert _client_reaches(PROVIDERS) == []
    assert _client_reaches(fixtures / "providers@030c0144") == []
    assert _client_reaches(fixtures / "providers@193e9f58") == ["openrouter.py:29"]
    (tmp_path / "fixture.py").write_text('def stop(delegate):\n    return getattr(delegate, "_client")\n')
    assert _client_reaches(tmp_path) == ["fixture.py:2"]
