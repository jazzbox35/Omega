"""Catalog interchange and nginx preparation, before the agent loses API keys.

Accept the installer's role-keyed records or LiteLLM-style model_list records.
The harness sees model_name/litellm_params records with credential references;
only nginx receives literal keys. This module uses only the standard library.
"""

import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


PROVIDERS = {
    "OpenAI": ("openai", "https://api.openai.com/v1/", "OPENAI_API_KEY"),
    "Anthropic": ("anthropic", "https://api.anthropic.com/v1/", "ANTHROPIC_API_KEY"),
    "ASICloud": ("openai", "https://inference.asicloud.cudos.org/v1/", "ASI_API_KEY"),
    "ASIOne": ("openai", "https://api.asi1.ai/v1/", "ASIONE_API_KEY"),
    "OpenRouter": ("openrouter", "https://openrouter.ai/api/v1/", "OPENROUTER_API_KEY"),
    "OpenAIAPI": ("openai", "http://host.docker.internal:11434/v1/", "OPENAIAPI_API_KEY"),
}


def normalize_catalog(value, first_only=False):
    """Return role-keyed named records; permit new roles without schema changes."""
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict) and "model_list" in value:
        value = value["model_list"]
    if isinstance(value, list):
        if first_only:
            value = value[:1]
        records = {}
        for record in value:
            role = record["model_name"]
            if role in records:
                raise ValueError("Duplicate router catalog role")
            records[role] = record
        value = records
    if not isinstance(value, dict) or not value or (not first_only and "routine" not in value):
        raise ValueError("router_catalog must contain a routine record")
    if first_only:
        role = next(iter(value))
        value = {role: value[role]}
    result = {}
    for role, record in value.items():
        if not isinstance(role, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", role):
            raise ValueError("Router roles must use lowercase letters, digits and underscores")
        if not isinstance(record, dict):
            raise ValueError("Each router catalog entry must be a record")
        params = dict(record.get("litellm_params", {}))
        provider = record.get("provider")
        if not provider:
            prefix = str(params.get("model", "")).partition("/")[0]
            provider = {"openai": "OpenAI", "anthropic": "Anthropic",
                        "openrouter": "OpenRouter"}.get(prefix)
        if not isinstance(provider, str) or not provider:
            raise ValueError("Each catalog entry requires a provider")
        model = record.get("model")
        if model is None:
            model = str(params.get("model", "")).partition("/")[2]
        prefix, base, key_var = PROVIDERS.get(provider, (provider.lower(), "", ""))
        base = record.get("openaiapi_url") or params.get("api_base") or base
        key_var = record.get("api_token_var") or key_var
        if not all(isinstance(item, str) for item in (model, base, key_var)):
            raise ValueError("Catalog model, api_base and api_token_var must be strings")
        params.setdefault("model", f"{prefix}/{model}")
        params.setdefault("api_base", base)
        params.setdefault("api_key", f"os.environ/{key_var}")
        if not isinstance(params["api_key"], str) or not isinstance(record.get("token", ""), str):
            raise ValueError("Catalog API keys must be strings")
        result[role] = {
            "model_name": role, "provider": provider, "model": model,
            "litellm_params": params, "api_token_var": key_var,
            "gateway_route": record.get("gateway_route", f"catalog/{role}"),
        }
        if "token" in record:
            result[role]["token"] = record["token"]
    return result


def _nginx_literal(value):
    # nginx performs variable expansion even in quoted strings.
    value = str(value)
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Control characters are not allowed in gateway settings")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$') + '"'


def prepare_gateway(raw, routes_path, catalog_path, first_only=False):
    catalog = normalize_catalog(raw, first_only=first_only)
    routes = []
    for role, record in catalog.items():
        params = record["litellm_params"]
        base = params["api_base"].rstrip("/") + "/"
        url = urlsplit(base)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError("Catalog api_base must be an HTTP(S) URL without credentials")
        if url.query or url.fragment:
            raise ValueError("Catalog api_base must not contain a query or fragment")
        key = record.pop("token", None)
        if key is None:
            key = params.get("api_key", "")
            if key.startswith("os.environ/"):
                key = os.environ.get(key[len("os.environ/"):], "")
        if not key:
            raise ValueError(f"Missing API key for router role {role}")
        # Never trust a catalog-supplied route as nginx configuration text.
        record["gateway_route"] = f"catalog/{role}"
        routes.append(f'''location /catalog/{role}/ {{
    proxy_pass {_nginx_literal(base)};
    proxy_set_header Authorization {_nginx_literal('Bearer ' + key)};
    proxy_set_header Host {_nginx_literal(url.netloc)};
    proxy_set_header Content-Type $content_type;
    proxy_ssl_server_name on;
    proxy_ssl_name {_nginx_literal(url.hostname)};
    proxy_http_version 1.1;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
}}''')
        params["api_key"] = f"os.environ/OMEGA_ROUTER_{role.upper()}_API_KEY"
    Path(routes_path).write_text("\n".join(routes), encoding="utf-8")
    os.chmod(routes_path, 0o600)
    # This copy contains no API key and is readable by the sandboxed agent.
    Path(catalog_path).write_text(json.dumps({"model_list": list(catalog.values())}), encoding="utf-8")
    os.chmod(catalog_path, 0o644)


if __name__ == "__main__":
    import config
    config.init_config(sys.argv[3:])
    raw = config.config_get_by_key("router_catalog")
    source = config.config_get_by_key("router_catalog_file")
    if not raw and source:
        raw = Path(source).read_text(encoding="utf-8")
    if raw:
        prepare_gateway(raw, sys.argv[1], sys.argv[2],
                        first_only=config.config_get_by_key("router") == "none")
        print(sys.argv[2])
    else:
        Path(sys.argv[1]).write_text("", encoding="utf-8")
        os.chmod(sys.argv[1], 0o600)
