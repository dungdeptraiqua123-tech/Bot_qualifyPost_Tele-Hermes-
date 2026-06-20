from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class HermesClient:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float

    async def chat_completion(self, *, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Hermes response shape: {data!r}") from exc

        if not isinstance(content, str):
            raise RuntimeError(f"Unexpected Hermes message content: {content!r}")
        return content.strip()
