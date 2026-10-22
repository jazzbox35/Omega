import config
import logging
from typing import List
import json
import copy
import os
from pathlib import Path
from router_catalog import normalize_catalog

logger = logging.getLogger(__name__)

_llmProviderRegistry = {}

class LLMTool:

    def __init__(self):
        self.name = None
        self.description = None
        self.parameters = []

    def with_name(self, name):
        self.name = name
        return self

    def with_description(self, description):
        self.description = description
        return self

    def add_parameter(self, parameter):
        self.parameters.append(parameter)
        return self

    def with_parameters(self, parameters):
        self.parameters = parameters
        return self

    def __repr__(self):
        return f"LLMTool[name={self.name!r}, description={self.description!r}, parameters={self.parameters!r}]"

class LLMToolParameter:

    def with_name(self, name):
        self.name = name
        return self

    def __repr__(self):
        return f"LLMToolParameter[name={self.name!r}]"

class LLMToolCall:

    def __init__(self):
        self.name = None
        self.id = None
        self.error = None
        self.arguments = {}
        self.tool = None

    def with_name(self, name):
        self.name = name
        return self

    def with_id(self, id):
        self.id = id
        return self

    def is_error(self):
        return bool(self.error)

    def with_error(self, error):
        self.error = error
        return self

    def set_error(self, error):
        self.error = error

    def add_argument(self, name, value):
        self.arguments[name] = value
        return self

    def with_arguments(self, arguments):
        self.arguments = arguments
        return self

    def set_tool(self, tool: LLMTool):
        self.tool = tool

    def __repr__(self):
        return f"LLMToolCall[id={self.id!r},name={self.name!r},arguments={self.arguments!r},error={self.error!r}]"

    def __eq__(self, other):
        return (self.name == other.name
                and self.id == other.id
                and self.error == other.error
                and self.arguments == other.arguments
                and self.tool == other.tool)

class LLMMessage:

    def __init__(self):
        self.role = None
        self.content = None

    def with_role(self, role):
        self.role = role
        return self

    def with_content(self, content):
        self.content = content
        return self

    def __repr__(self):
        return f"LLMMessage[role={self.role!r},content={self.content!r}]"

class LLMToolCallResponseMessage(LLMMessage):

    def __init__(self):
        super().__init__()
        self.callid = None

    def with_callid(self, callid):
        self.callid = callid
        return self

    def __repr__(self):
        return f"LLMToolCallResponseMessage[role={self.role!r},content={self.content!r},callid={self.callid!r}]"

class LLMToolCallMessage(LLMMessage):

    def __init__(self):
        super().__init__()
        self.calls: [LLMToolCall] = []

    def with_calls(self, calls):
        self.calls = calls
        return self

    def __repr__(self):
        return f"LLMToolCallMessage[role={self.role!r},content={self.content!r},calls={self.calls!r}]"

class LLMRequest:

    def __init__(self):
        self.messages: [LLMMessage] = []
        self.max_tokens = config.config_get_by_key("maxOutputToken")
        self.reasoning_mode = config.config_get_by_key("reasoningMode")
        self.tools = []
        self.tool_by_name = {}
        self.provider = ""
        self.model = ""
        self.router = "none"

    def add_message(self, message):
        self.messages.append(message)
        return self

    def with_messages(self, messages):
        self.messages = messages
        return self

    def with_max_tokens(self, max_tokens):
        self.max_tokens = max_tokens
        return self

    def with_reasoning_mode(self, reasoning_mode):
        self.reasoning_mode = reasoning_mode
        return self

    def add_tool(self, tool: LLMTool):
        if tool.name in self.tool_by_name:
            self.tools.remove(self.tool_by_name[tool.name])
            del self.tool_by_name[tool.name]
        self.tools.append(tool)
        self.tool_by_name[tool.name] = tool
        return self

    def with_tools(self, tools: List[LLMTool]):
        self.tools = tools
        self.tool_by_name = { t.name: t for t in tools }
        return self

    def has_tool(self, name):
        return name in self.tool_by_name

    def get_tool(self, name):
        return self.tool_by_name.get(name, None)

    def __repr__(self):
        return f"LLMRequest[messages={self.messages!r}, max_tokens={self.max_tokens!r}, reasoning_mode={self.reasoning_mode!r}, tools={self.tools!r}]"

class LLMResponse:

    def __init__(self):
        self.calls: List[LLMToolCall] = []
        self.error = None

    def add_tool_call(self, call: LLMToolCall):
        self.calls.append(call)
        return self

    def with_error(self, error: str):
        self.error = error
        return self

    def is_error(self):
        return bool(self.error)

    def __repr__(self):
        return f"LLMResponse[calls={self.calls!r},error={self.error!r}]"

    def __eq__(self, other):
        return self.calls == other.calls and self.error == other.error

class LLMProvider:
    """LLM provider implementation"""

    def start(self) -> None:
        """Configure and start LLM provider"""
        pass

    def stop(self) -> None:
        """Stop and LLM provider and free resources"""
        pass

    def chat(self, request: LLMRequest) -> LLMResponse:
        """Chat with LLM provider"""
        raise NotImplementedError()

def registerLLMProvider(id: str, provider: LLMProvider) -> None:
    """
    Register LLM provider in the registry.

    Arguments:
    id: the identifier of the plugin which is used to load it
    provider: the implementation of the provider
    """
    global _llmProviderRegistry
    logger.info(f"registerLLMProvider: registering LLM provider {id}")
    _llmProviderRegistry[id] = provider

_llmprovider: LLMProvider = None
_catalogue = {}
_role_providers = {}
_llmRouterRegistry = set()
_router = "none"
_last_outcome = None

# BEGIN DEBUG: cumulative provider calls by catalog role (since startup).
_debug_role_calls = {}


def debugRouterCallTotals(message):
    roles = dict.fromkeys([*_catalogue, *_debug_role_calls])
    totals = ", ".join(f"{role}={_debug_role_calls.get(role, 0)}" for role in roles)
    return f"{message}\n[DEBUG router calls: {totals or 'none'}]"
# END DEBUG


def registerLLMRouter(name):
    """A MeTTa plugin registers its function separately under this name."""
    name = str(name)
    if name in _llmRouterRegistry:
        raise ValueError(f"Router {name!r} is already registered")
    _llmRouterRegistry.add(name)
    return name


def llmRouterStart():
    global _router
    configured = config.config_get_by_key("router")
    _router = str(configured or ("default" if len(_catalogue) > 1 else "none"))
    if len(_catalogue) == 1:
        _router = "none"
    if _router not in ("none", "default"):
        raise ValueError("Phase 1 supports router=default or router=none")
    if _router != "none" and _router not in _llmRouterRegistry:
        raise ValueError(f"Router {_router!r} is not registered")
    if _router == "default" and "premium" not in _catalogue:
        raise ValueError("The default router requires a premium catalog record")
    return _router


def llmRoutingEnabled():
    return _router != "none"


def llmCatalogueGet():
    """Give plugins a copy of named records, without credentials."""
    return copy.deepcopy(list(_catalogue.values()))


def llmLastOutcome():
    return _last_outcome

def llmProviderStart(provider):
    """Start an independent provider instance for every catalog record."""
    global _llmprovider, _catalogue, _role_providers, _last_outcome
    for instance in _role_providers.values():
        instance.stop()
    _role_providers = {}
    _catalogue = {}
    _last_outcome = None
    # BEGIN DEBUG: reset totals when provider setup starts.
    _debug_role_calls.clear()
    # END DEBUG
    from router_policy import reset
    reset()
    catalog_file = config.config_get_by_key("router_catalog_file")
    raw = (Path(catalog_file).read_text(encoding="utf-8") if catalog_file
           else config.config_get_by_key("router_catalog"))
    if raw:
        _catalogue = normalize_catalog(
            raw, first_only=config.config_get_by_key("router") == "none")
        try:
            for role, record in _catalogue.items():
                prototype = _llmProviderRegistry.get(record["provider"])
                if prototype is None:
                    raise ValueError(f"Provider {record['provider']!r} is not registered")
                instance = copy.deepcopy(prototype)
                params = record["litellm_params"]
                values = {
                    "api_token_var": record["api_token_var"],
                    "provider_gateway_route": record["gateway_route"],
                    "provider_api_base": params["api_base"],
                    "openaiapi_url": params["api_base"],
                }
                # Direct standalone calls can use a literal key or environment
                # reference. Container catalogs have already been scrubbed.
                key = record.get("token", params.get("api_key", ""))
                if key.startswith("os.environ/"):
                    key = os.environ.get(key[len("os.environ/"):], "")
                values["provider_api_key"] = key or None
                if record["model"]:
                    values["model"] = record["model"]
                with config.provider_config(values):
                    instance.start()
                # Materialize provider defaults so router choices name the exact model.
                delegate = getattr(instance, "delegate", None)
                record["model"] = getattr(delegate, "_model_name", record["model"])
                prefix = params["model"].partition("/")[0]
                params["model"] = f"{prefix}/{record['model']}"
                record.pop("token", None)
                params["api_key"] = f"os.environ/OMEGA_ROUTER_{role.upper()}_API_KEY"
                _role_providers[role] = instance
        except Exception:
            for instance in _role_providers.values():
                instance.stop()
            _role_providers = {}
            raise
        _llmprovider = next(iter(_role_providers.values()))
        return

    # Preserve standalone installations configured with only provider/model.
    _llmprovider = _llmProviderRegistry.get(provider, None)
    if _llmprovider is None:
        error = f"llmProviderStart: LLM provider plugin {provider} is not registered"
        logger.error(error)
        raise RuntimeError(error)
    _llmprovider.start()
    model = getattr(getattr(_llmprovider, "delegate", None), "_model_name", "")
    _catalogue = {"routine": {"model_name": "routine", "provider": provider,
                              "model": model, "litellm_params": {"model": model}}}
    _role_providers = {"routine": _llmprovider}


def llmProviderChatRouted(request, selection):
    """Validate the router's explicit provider/model, then dispatch unchanged.

    A role may accompany the pair to disambiguate credentials and endpoints.
    A bare pair is accepted only when it identifies exactly one catalog record.
    """
    role = None
    if isinstance(selection, dict):
        provider, model = selection.get("provider"), selection.get("model")
        role = selection.get("role")
    elif isinstance(selection, (tuple, list)) and len(selection) == 2:
        provider, model = selection
    else:
        return llmRouterRaised("Router must return an explicit provider and model")
    if not isinstance(provider, str) or not isinstance(model, str):
        return llmRouterRaised("Router provider and model must be strings")
    matches = [name for name, record in _catalogue.items()
               if (record["provider"], record["model"]) == (provider, model)
               and (role is None or name == role)]
    if len(matches) != 1:
        return llmRouterRaised("Router provider/model selection is absent or ambiguous in the catalog")
    return _llmProviderChatRecord(request, matches[0], provider, model)


def _llmProviderChatRecord(request, role, provider, model):
    """Execute an already selected record, including the routine-only path."""
    global _last_outcome
    request.provider = provider
    request.model = model
    request.router = _router
    logger.info("LLM routing: role=%s provider=%s model=%s", role, request.provider, request.model)
    # BEGIN DEBUG: count each harness call, including failed calls, once.
    _debug_role_calls[role] = _debug_role_calls.get(role, 0) + 1
    # END DEBUG
    try:
        response = _validate_response(request, _role_providers[role].chat(request))
    except Exception:
        logger.exception("Exception while calling catalog role %s", role)
        response = LLMResponse().with_error(f"Provider call failed for role {role}")
    _last_outcome = {"role": role, "error": response.error,
                     "failed": response.is_error() or any(call.is_error() for call in response.calls)}
    return response

def llmRouterRaised(error):
    global _last_outcome
    logger.error("Router failed; no provider called: %s", error)
    _last_outcome = {"failed": True, "error": str(error)}
    return LLMResponse().with_error("Router failed to select a valid catalog record")

def llmProviderChat(request):
    """Chat via selected LLM provider"""
    if _catalogue:
        role = next(iter(_catalogue)) if _router == "none" else "routine"
        record = _catalogue[role]
        return _llmProviderChatRecord(request, role, record["provider"], record["model"])
    global _llmprovider
    # BEGIN DEBUG: cover legacy calls made without a catalog.
    _debug_role_calls["routine"] = _debug_role_calls.get("routine", 0) + 1
    # END DEBUG
    try:
        response = _llmprovider.chat(request)
        return _validate_response(request, response)
    except Exception:
        logger.exception("Exception while getting LLM response")
        return LLMResponse()

def _validate_response(request: LLMRequest, response: LLMResponse) -> LLMResponse:
    if not response.calls and not response.is_error():
        return response.with_error("List of tool calls is empty")

    for call in response.calls:
        if call.is_error():
            continue
        if not request.has_tool(call.name):
            call.set_error(f"Unknown tool: {call.name!r}")
            continue
        call.set_tool(request.get_tool(call.name))
        for parameter in call.tool.parameters:
            if not parameter.name in call.arguments:
                call.set_error(f"Call tool parameter is not set: tool: {call.name!r}, parameter: {parameter.name!r}")
                break
            if not isinstance(call.arguments[parameter.name], str):
                call.set_error(f"Call tool parameter is not a string: tool: {call.name!r}, parameter: {parameter.name!r}")
                break
    return response

def getTools(skills):
    """Form a list of tools for LLM from the list of skills"""
    tools = []
    for name, desc, params in skills:
        tool = LLMTool().with_name(name).with_description(desc)
        for param in params:
            tool.add_parameter(LLMToolParameter().with_name(param))
        tools.append(tool)
    return tools

def llmRequestMessage(role, content):
    return LLMMessage().with_role(role).with_content(content)

def llmToolCallResponseMessage(role, callid, content):
    return (LLMToolCallResponseMessage().with_role(role)
                                        .with_callid(callid)
                                        .with_content(content))

def llmToolCallMessage(role, calls: [LLMToolCall], content):
    return (LLMToolCallMessage().with_role(role)
                                .with_calls(calls)
                                .with_content(content))

def llmRequest(prompt, episodes, max_tokens, reasoning_mode, tools):
    return (LLMRequest().with_messages([prompt] + episodes)
                       .with_max_tokens(max_tokens)
                       .with_reasoning_mode(reasoning_mode)
                       .with_tools(tools))

def llmResponseIsEmpty(response: LLMResponse):
    return len(response.calls) == 0

def llmResponseCalls(response: LLMResponse):
    return response.calls

def llmResponseIsError(response: LLMResponse):
    return response.is_error()

def llmResponseGetError(response: LLMResponse):
    return response.error

def llmToolCallGetName(call: LLMToolCall):
    return call.name

def llmToolCallGetId(call: LLMToolCall):
    return call.id

def llmToolCallGetArguments(call: LLMToolCall):
    return call.arguments

def llmToolCallIsError(call: LLMToolCall):
    return bool(call.error)

def llmToolCallGetError(call: LLMToolCall):
    return call.error

ESCAPE = str.maketrans({ '"': '\\"', '\\': '\\\\' })

def llmToolCallToSExpr(call: LLMToolCall):
    sexpr = f"({call.name} "
    if not call.is_error():
        for parameter in call.tool.parameters:
            if parameter.name in call.arguments:
                arg = call.arguments[parameter.name]
                arg = arg.translate(ESCAPE)
                sexpr = sexpr + f"\"{arg}\" "
    else:
        for arg in call.arguments.values():
            if not isinstance(arg, str):
                arg = json.dumps(arg, ensure_ascii=False)
            arg = arg.translate(ESCAPE)
            sexpr = sexpr + f"\"{arg}\" "

    sexpr = sexpr[:-1] + ")"
    if call.is_error():
        sexpr = f"(Error {sexpr} \"{str(call.error).translate(ESCAPE)}\")"
    return f"({call.id} {sexpr})"

def llmResponseToSExpr(response: LLMResponse) -> str:
    if response.is_error():
        return f"(Error () \"{str(response.error).translate(ESCAPE)}\")"
    else:
        sexpr = "("
        for call in response.calls:
            sexpr = sexpr + llmToolCallToSExpr(call)
        return sexpr + ")"
