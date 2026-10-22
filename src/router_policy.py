"""Text inspection and bounded premium state for the default MeTTa router."""

import re
from config import config_get_by_key

_remaining = 0
_seen_messages = set()


def reset():
    global _remaining, _seen_messages
    _remaining = 0
    _seen_messages = set()


def _positive_setting(name, default):
    value = config_get_by_key(name, default)
    if isinstance(value, bool) or not str(value).isdigit() or int(value) < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _terms(text):
    return set(re.findall(r"[\w]+", text.casefold()))


def catalog_selection(catalogue, role):
    """Resolve the policy's role inside the router, before returning its choice."""
    for record in catalogue:
        if record["model_name"] == role:
            return {"provider": record["provider"], "model": record["model"],
                    "role": role}
    raise ValueError(f"Router catalog has no {role!r} record")


def needs_premium(request, last_outcome):
    """Inspect real user/tool messages, never system instructions or role tags.

    Deep reasoning holds for N calls, including the triggering call. A repeated
    historical message cannot renew the hold. Sender prefixes in channel text
    distinguish users; multiple messages alone do not imply multiple users.
    """
    global _remaining, _seen_messages
    messages = [m for m in request.messages if m.role in ("user", "tool")]
    # Retain references through the request list; identities identify newly added
    # messages even when their text is identical to an earlier user request.
    current_ids = {id(m) for m in messages}
    new_messages = [m for m in messages if id(m) not in _seen_messages]
    _seen_messages = current_ids
    text = "\n".join(str(m.content or "") for m in messages)
    terms = _terms(text)
    new_terms = _terms("\n".join(str(m.content or "") for m in new_messages))
    if "deep_reasoning" in new_terms:
        _remaining = _positive_setting("router_premium_turns", 3)
    held = _remaining > 0
    if held:
        _remaining -= 1

    users = set()
    for message in messages:
        if message.role != "user":
            continue
        sender = getattr(message, "user_id", None)
        if sender:
            users.add(str(sender))
        # IRC, Slack and Telegram present incoming text as 'sender: message'.
        content = str(message.content or "")
        for segment in re.split(r"\s+\|\s+|\n", content):
            segment = re.sub(r"^\s*\[-?\d*\]\s*\[\d*\]\s*", "", segment)
            slack = re.match(r"\s*<@([^>]+)>\s*\([^)]*\):", segment)
            sender = re.match(r"\s*([^:\[\]]{1,100}):\s", segment)
            if slack:
                users.add(slack.group(1))
            elif sender:
                users.add(sender.group(1).strip())

    keywords = config_get_by_key("router_escalate_keywords", "premium,premium_model,alert_failure,alert_failed,error")
    keyword_set = {str(word).strip().casefold() for word in str(keywords).split(",") if str(word).strip()}
    return bool(held or terms.intersection(keyword_set) or len(users) > 1
                or len(messages) >= _positive_setting("router_escalate_items", 9)
                or (isinstance(last_outcome, dict) and last_outcome.get("failed")))
