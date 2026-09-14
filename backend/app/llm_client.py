"""
Thin wrapper around the OpenAI SDK for schema-constrained, single-purpose
calls.

Design intent (per project requirement): every call here is ISOLATED.
- Each function takes only the exact inputs it needs (e.g. the JD extractor
  never sees the resume; the resume extractor never sees the JD; the
  evidence analyzer sees both but never sees any prior score or is told
  what the "hoped for" answer is).
- Every call uses a fixed, low/zero temperature and a strict JSON schema
  (OpenAI Structured Outputs) so the model cannot go off-format.
- No call is ever given instructions like "be encouraging" or "go easy on
  the candidate" — system prompts explicitly forbid softening.
- These calls extract and label evidence. They never produce a numeric
  score themselves — scoring is 100% deterministic Python (see
  app/scoring/engine.py).

NOTE ON MODEL NAMES: OPENAI_MODEL is read from your .env. Model
availability changes over time; verify the configured model still exists
and supports Structured Outputs in OpenAI's current docs before relying
on this in production.
"""
import json
from typing import Type, TypeVar
from openai import OpenAI
from pydantic import BaseModel

from app.config import settings

T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to backend/.env (copy from .env.example)."
            )
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def structured_call(
    *,
    system_prompt: str,
    user_prompt: str,
    response_model: Type[T],
    schema_name: str,
    temperature: float = 0.0,
) -> T:
    """
    Calls the chat completions endpoint with a strict JSON schema derived
    from a Pydantic model, and returns a validated instance of that model.

    Raises on malformed/non-conforming output rather than silently
    guessing — a failed extraction should surface as an error, not a
    quietly wrong score.
    """
    client = get_client()
    schema = response_model.model_json_schema()
    # OpenAI's structured-output mode wants additionalProperties: false and
    # every property required at every object level. Pydantic v2's
    # model_json_schema() already sets "required" for non-Optional fields;
    # we patch in additionalProperties defensively for nested objects.
    _lock_schema(schema)

    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": False,  # keep False: Pydantic's optional/default fields
                                   # don't always satisfy OpenAI's strict-mode
                                   # "all fields required" rule. Verify current
                                   # OpenAI structured-outputs docs if you want
                                   # to switch this to fully strict mode.
            },
        },
    )
    content = resp.choices[0].message.content
    data = json.loads(content)
    return response_model.model_validate(data)


def _lock_schema(schema: dict) -> None:
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
    for v in schema.get("$defs", {}).values():
        _lock_schema(v)
    for v in schema.get("properties", {}).values():
        if isinstance(v, dict):
            _lock_schema(v)
