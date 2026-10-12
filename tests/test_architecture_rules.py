"""Architecture rules for LLM routing (ADR-0001, OMEGA-376 increment 1, R2).

A router decides and returns the envelope; a provider calls what the envelope
names and never branches on a routing concept.

Check 1, the router holds no credential and makes no call, over every .py and
.metta file under routers/:
  check1-metta-py     a .metta router uses py-call, py-atom, py-dot or import!
  check1-config-key   a configuration read (configGetByKey / configure / config
                      in MeTTa, config_get_by_key in Python) whose key is not a
                      literal matching CONFIG_KEY_ALLOWED
  check1-py-import    a .py router imports openai, requests, httpx, urllib,
                      socket or providers
  check1-py-env       a .py router reads os.environ or getenv

Check 2, the provider decides nothing, over every .py file under providers/,
with no exemption:
  check2a-attr        an LLMRequest parameter is read for anything but
                      LLMREQUEST_ALLOWED, or passed to getattr
  check2b-word        an identifier, comment or string literal contains a word
                      part in FORBIDDEN_WORDS ("router" is not one:
                      OpenRouterProvider splits to it; check 2a covers
                      request.router). String literals are included so that a
                      comparison such as `== "premium_model"` is caught too

Known limits, by design: calls are not followed into src/ helpers (check 1);
aliasing is not followed, and outside the provider interface (methods named
chat or convert_request) an unannotated parameter is not treated as an
LLMRequest (check 2a).
"""
import ast
import io
import pathlib
import re
import tokenize

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "res" / "architecture"

CONFIG_KEY_ALLOWED = re.compile(r"^(router_[a-z_]+|provider|model|premium_model|[a-z]+_model)$")
METTA_PY_FORMS = ("py-call", "py-atom", "py-dot", "import!")
METTA_CONFIG_FORMS = ("configGetByKey", "configure", "config")
PY_FORBIDDEN_IMPORTS = {"openai", "requests", "httpx", "urllib", "socket", "providers"}
LLMREQUEST_ALLOWED = {"messages", "max_tokens", "reasoning_mode", "tools", "model"}
PROVIDER_INTERFACE = {"chat", "convert_request"}
FORBIDDEN_WORDS = {"tier", "tiers", "economy", "premium"}


def _violation(path, root, line, rule, detail):
    return f"{path.relative_to(root.parent)}:{line} {rule} {detail}"


# --- check 1 ---------------------------------------------------------------

def _metta_code_lines(text):
    """Yield (line number, code) with ';' comments removed outside strings."""
    for number, line in enumerate(text.splitlines(), 1):
        code, in_string = [], False
        for char in line:
            if char == '"':
                in_string = not in_string
            elif char == ";" and not in_string:
                break
            code.append(char)
        yield number, "".join(code)


def _check1_metta(path, root):
    found = []
    for number, code in _metta_code_lines(path.read_text()):
        for form in METTA_PY_FORMS:
            if re.search(r"\(\s*" + re.escape(form) + r"(?=[\s()])", code):
                found.append(_violation(path, root, number, "check1-metta-py", form))
        for match in re.finditer(r"\(\s*(" + "|".join(METTA_CONFIG_FORMS) + r")\s+(\S+)", code):
            key = match.group(2).rstrip(")")
            literal = key.strip('"') if re.fullmatch(r'"[^"]*"|[A-Za-z_][A-Za-z0-9_]*', key) else None
            if literal is None or not CONFIG_KEY_ALLOWED.match(literal):
                found.append(_violation(path, root, number, "check1-config-key", key))
    return found


def _check1_py(path, root):
    found = []
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                if name.split(".")[0] in PY_FORBIDDEN_IMPORTS:
                    found.append(_violation(path, root, node.lineno, "check1-py-import", name))
        elif isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv"):
            found.append(_violation(path, root, node.lineno, "check1-py-env", node.attr))
        elif isinstance(node, ast.Name) and node.id in ("environ", "getenv"):
            found.append(_violation(path, root, node.lineno, "check1-py-env", node.id))
        elif isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "config_get_by_key":
            key = node.args[0] if node.args else None
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str) and CONFIG_KEY_ALLOWED.match(key.value)):
                found.append(_violation(path, root, node.lineno, "check1-config-key",
                                        ast.unparse(key) if key is not None else "<none>"))
    return found


def check_routers(root):
    """Return (scanned files, violations) for routers/ under root, or (None, [])
    when root has no routers/ (the check is then vacuous)."""
    routers = root / "routers"
    if not routers.is_dir():
        return None, []
    scanned = sorted(p for p in routers.rglob("*") if p.suffix in (".py", ".metta"))
    found = []
    for path in scanned:
        found += _check1_metta(path, routers) if path.suffix == ".metta" else _check1_py(path, routers)
    return [str(p.relative_to(root)) for p in scanned], found


# --- check 2 ---------------------------------------------------------------

def _is_llmrequest(annotation):
    if annotation is None:
        return False
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value.split(".")[-1] == "LLMRequest"
    return getattr(annotation, "id", getattr(annotation, "attr", None)) == "LLMRequest"


def _request_params(function):
    params = function.args.posonlyargs + function.args.args + function.args.kwonlyargs
    names = {p.arg for p in params if _is_llmrequest(p.annotation)}
    if function.name in PROVIDER_INTERFACE:
        first = [p for p in function.args.posonlyargs + function.args.args if p.arg != "self"]
        if first:
            names.add(first[0].arg)
    return names


def _check2a(path, root, tree):
    found = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = _request_params(function)
        for node in ast.walk(function):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id in params and node.attr not in LLMREQUEST_ALLOWED:
                found.append(_violation(path, root, node.lineno, "check2a-attr", f"{node.value.id}.{node.attr}"))
            elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "getattr" \
                    and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in params:
                found.append(_violation(path, root, node.lineno, "check2a-attr", f"getattr({node.args[0].id}, ...)"))
    return found


def _word_parts(text):
    for chunk in re.split(r"[^A-Za-z0-9]+", text):
        for part in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+", chunk):
            yield part.lower()


def _check2b(path, root, source):
    found = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.NAME, tokenize.COMMENT, tokenize.STRING):
            hits = sorted(FORBIDDEN_WORDS.intersection(_word_parts(token.string)))
            if hits:
                found.append(_violation(path, root, token.start[0], "check2b-word", f"{','.join(hits)} in {token.string!r}"))
    return found


def check_providers(root):
    """Return the violations of check 2 for providers/ under root."""
    providers = root / "providers"
    found = []
    for path in sorted(providers.glob("*.py")):
        source = path.read_text()
        found += _check2a(path, providers, ast.parse(source, str(path)))
        found += _check2b(path, providers, source)
    return found


def _locations(violations, rule=None):
    return {v.split(" ")[0] for v in violations if rule is None or v.split(" ")[1] == rule}


# --- the rules, on this tree -----------------------------------------------

def test_routers_hold_no_credential_and_make_no_call():
    scanned, violations = check_routers(REPO)
    if scanned is None:
        print("check 1 vacuous: no routers/")
        return
    print("check 1 scanned:", scanned)
    assert scanned, "routers/ exists but no .py or .metta file was scanned"
    assert violations == []


def test_providers_decide_nothing():
    assert check_providers(REPO) == []


# --- proof that the rules bite ---------------------------------------------

def _fixture_root(tmp_path, sha):
    """A tree whose providers/ is the verbatim copy taken at sha."""
    (tmp_path / "providers").symlink_to(FIXTURES / f"providers@{sha}", target_is_directory=True)
    return tmp_path


def test_check2_flags_pr373_provider_side_routing(tmp_path):
    """R2-T1: on providers/ @ 193e9f58, check 2 flags at least QA's locations."""
    violations = check_providers(_fixture_root(tmp_path, "193e9f58"))
    expected_2b = {"providers/openrouter.py:20", "providers/openrouter.py:34", "providers/openrouter.py:36",
                   "providers/openrouter.py:38", "providers/openrouter.py:39", "providers/openaiapi.py:30", "providers/openai.py:26",
                   "providers/mockprovider.py:17", "providers/asione.py:40"}
    assert expected_2b <= _locations(violations, "check2b-word"), violations
    assert {"providers/openrouter.py:34", "providers/openrouter.py:39"} <= _locations(violations, "check2a-attr"), violations


def test_both_checks_pass_on_the_baseline(tmp_path):
    """R2-T2: on providers/ @ 030c0144 (no routers/), both checks pass; check 1 is vacuous."""
    root = _fixture_root(tmp_path, "030c0144")
    scanned, violations = check_routers(root)
    print("check 1 vacuous at 030c0144: no routers/" if scanned is None else f"check 1 scanned: {scanned}")
    assert scanned is None and violations == []
    assert check_providers(root) == []


def _routers(tmp_path, files):
    for name, text in files.items():
        (tmp_path / "routers").mkdir(exist_ok=True)
        (tmp_path / "routers" / name).write_text(text)
    return tmp_path


def test_check1_config_key_must_be_an_allowed_literal(tmp_path):
    """R2-T4: a non-literal configuration key fails check1-config-key; an allowed literal passes."""
    root = _routers(tmp_path, {
        "computed.metta": '(= (k) (configGetByKey (string-concat "router_" "x") 4))\n',
        "literal.metta": "(= (n) (configGetByKey router_escalate_items 4))\n",
        "literal.py": 'from config import config_get_by_key\nN = config_get_by_key("router_escalate_items", 4)\n',
        "secret.py": 'from config import config_get_by_key\nK = config_get_by_key("OPENROUTER_API_KEY")\n',
    })
    _, violations = check_routers(root)
    assert _locations(violations, "check1-config-key") == {"routers/computed.metta:1", "routers/secret.py:2"}, violations


def test_check2a_covers_the_unannotated_provider_interface(tmp_path):
    """R2-T5: an unannotated first parameter of chat is still an LLMRequest; of
    any other method it is not (the documented limit)."""
    (tmp_path / "providers").mkdir()
    (tmp_path / "providers" / "fixture.py").write_text(
        "class P:\n"
        "    def chat(self, args):\n"
        "        return args.router\n"
        "    def helper(self, args):\n"
        "        return args.router\n")
    assert _locations(check_providers(tmp_path), "check2a-attr") == {"providers/fixture.py:3"}


def test_check1_scans_metta_files(tmp_path):
    """R2-T6: a routers/ holding only a .metta file is scanned, not skipped."""
    scanned, violations = check_routers(_routers(tmp_path, {"only.metta": "(= (r $e) $e)\n"}))
    print("check 1 scanned:", scanned)
    assert scanned == ["routers/only.metta"] and violations == []


@pytest.mark.parametrize("rule, path, text", [
    ("check1-metta-py", "x.metta", '(= (k) (py-call (os.getenv "OPENROUTER_API_KEY")))\n'),
    ("check1-py-env", "x.py", 'import os\nK = os.environ["OPENROUTER_API_KEY"]\n'),
    ("check1-py-import", "x.py", "import requests\n"),
], ids=["metta-py-call", "py-environ", "py-import"])
def test_check1_rules_name_file_line_and_rule(tmp_path, rule, path, text):
    """R2-FR3: every failure names the file, the line and the rule."""
    _, violations = check_routers(_routers(tmp_path, {path: text}))
    assert any(v.startswith(f"routers/{path}:") and f" {rule} " in v for v in violations), violations
