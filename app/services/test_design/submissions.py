"""Database-backed Web submission identity; no process-local correctness locks."""

import hashlib
import json
import re


_REQUEST_KEY = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")


class GenerationReplay(Exception):
    def __init__(self, session_id):
        self.session_id = session_id


def valid_request_key(value):
    return isinstance(value, str) and _REQUEST_KEY.fullmatch(value) is not None


def submission_fingerprint(context, project_id, version_id, provider):
    # No credentials or untrusted exception text enter this identity or the UI.
    payload = {
        "project_id": project_id,
        "version_id": version_id,
        "title": context.title,
        "requirement_text": context.requirement_text,
        "provider": provider.provider_name,
        "model": getattr(provider, "provider_model", None),
        "base_url": getattr(provider, "base_url", None),
        "max_tokens": getattr(provider, "max_output_tokens", None),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
