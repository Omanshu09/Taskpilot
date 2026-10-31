import json
import re
import time
from typing import Any

from groq import Groq

from app.config import settings


class ModelError(RuntimeError):
    pass


class GroqService:
    attempts = 3
    backoff_seconds = 20

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        self.model = model or settings.groq_model
        self.client = Groq(api_key=self.api_key) if self.api_key else None

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        if self.client is None:
            raise ModelError("GROQ_API_KEY is not configured")
        for attempt in range(self.attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0.25,
                    **({"response_format": {"type": "json_object"}} if json_mode else {}),
                    timeout=90,
                )
            except Exception as exc:
                limited = "rate" in str(exc).lower() or "429" in str(exc)
                if limited and attempt < self.attempts - 1:
                    time.sleep(self.backoff_seconds * (attempt + 1))
                    continue
                if limited:
                    raise ModelError("Groq rate limit reached. Please retry shortly.") from exc
                raise ModelError("The language model could not complete the request.") from exc
            content = response.choices[0].message.content
            if not content:
                raise ModelError("Groq returned an empty response")
            return content

    def structured(self, system: str, user: str) -> dict[str, Any]:
        raw = self.complete(system, user, True).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            return value
        except (json.JSONDecodeError, ValueError) as exc:
            raise ModelError("Groq returned malformed structured data.") from exc
