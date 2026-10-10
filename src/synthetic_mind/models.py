from __future__ import annotations

from typing import Protocol
import asyncio
import json


async def ollama_request(path: str, payload: dict | None = None, *, timeout: float = 60) -> dict:
    """Loopback-only HTTP; cancellation closes the inference connection."""
    async def request():
        reader, writer = await asyncio.open_connection("127.0.0.1", 11434)
        try:
            body = json.dumps(payload).encode() if payload is not None else b""
            method = "POST" if payload is not None else "GET"
            writer.write((f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
            await writer.drain()
            status = (await reader.readline()).decode().split()
            headers = {}
            while line := await reader.readline():
                if line == b"\r\n":
                    break
                key, value = line.decode().split(":", 1)
                headers[key.lower()] = value.strip()
            data = bytearray()
            if headers.get("transfer-encoding", "").lower() == "chunked":
                while True:
                    length = int((await reader.readline()).split(b";", 1)[0], 16)
                    if not length:
                        break
                    if len(data) + length > 2_000_000:
                        raise ValueError("Model response too large")
                    data.extend(await reader.readexactly(length))
                    await reader.readexactly(2)
            else:
                length = int(headers.get("content-length", 0))
                if length > 2_000_000:
                    raise ValueError("Model response too large")
                data.extend(await reader.readexactly(length) if length else await reader.read(2_000_001))
            value = json.loads(data)
            if len(status) < 2 or status[1] != "200":
                raise RuntimeError(value.get("error", "Ollama request failed"))
            return value
        finally:
            writer.close()
            await writer.wait_closed()
    return await asyncio.wait_for(request(), timeout)


class OllamaModelBackend:
    def __init__(self, model: str, schema: dict, think: bool | None = None):
        self.model, self.schema, self.think = model, schema, think
        self.metrics = {}

    async def generate(self, *, system: str, input_text: str, max_tokens: int = 384) -> str:
        response = await ollama_request("/api/chat", {"model": self.model,
            **({"think": self.think} if self.think is not None else {}),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": input_text}],
            "stream": False, "format": self.schema, "keep_alive": "5m",
            "options": {"num_ctx": 4096, "num_predict": max_tokens, "temperature": 0}})
        self.metrics = {key: response.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration")}
        if response.get("done_reason") == "length":
            raise RuntimeError("Model hit its output token limit before completing the response; check brain max_output_tokens")
        return response["message"]["content"]


class ModelBackend(Protocol):
    async def generate(self, *, system: str, input_text: str, max_tokens: int = 128) -> str: ...


class MockModelBackend:
    async def generate(self, *, system: str, input_text: str, max_tokens: int = 128) -> str:
        return "[MOCK] " + " ".join(input_text.split()[:max_tokens])
