"""Small, dependency-light helpers shared by Axon pages and services."""

import html
import json
import re


def clean_display_text(value):
    """Convert model text into compact plain text for user-facing panels."""
    text = html.unescape(str(value))
    text = re.sub(r"<\/?[a-zA-Z][^>]*>", "", text)
    text = re.sub(r"\b(?:div|span|br)\s+class\s*=\s*[\"'][^\"']*[\"']", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```(?:json|markdown|text)?", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_json(raw):
    """Parse common fenced or trailing-comma JSON returned by a model."""
    text = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def classify_error(error):
    """Map provider errors to the stable Axon error codes shown in the UI."""
    message = str(error).lower()
    if "api_key_invalid" in message or "api key not valid" in message or "unauthenticated" in message or "unauthorized" in message:
        return "AX-401"
    if "permission_denied" in message or "403" in message or "forbidden" in message:
        return "AX-403"
    if "resource_exhausted" in message or "quota" in message or "429" in message or "rate limit" in message or "too many" in message:
        return "AX-429"
    if "not_found" in message or "404" in message:
        return "AX-404"
    if "internal" in message or "500" in message:
        return "AX-500"
    if "unavailable" in message or "503" in message or "overloaded" in message:
        return "AX-503"
    return "AX-000"