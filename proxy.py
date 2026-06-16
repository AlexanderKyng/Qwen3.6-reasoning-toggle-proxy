#!/usr/bin/env python3
import json
import os
from dataclasses import dataclass

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")
REAL_MODEL = os.getenv("REAL_MODEL", "qwen3.6-27b")
LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "9999"))


@dataclass
class ModelProfile:
    enable_thinking: bool
    temperature: float
    top_p: float
    top_k: int
    min_p: float
    presence_penalty: float
    repetition_penalty: float
    preserve_thinking: bool


MODEL_MAP: dict[str, ModelProfile] = {
    "Qwen3.6-thinking": ModelProfile(
        enable_thinking=True,
        temperature=1.0,
        top_p=0.95,
        top_k=20,
        min_p=0.0,
        presence_penalty=1.5,
        repetition_penalty=1.0,
        preserve_thinking=False,
    ),
    "Qwen3.6-thinking-coding": ModelProfile(
        enable_thinking=True,
        temperature=0.6,
        top_p=0.95,
        top_k=20,
        min_p=0.0,
        presence_penalty=0.0,
        repetition_penalty=1.0,
        preserve_thinking=True,
    ),
    "Qwen3.6-instruct": ModelProfile(
        enable_thinking=False,
        temperature=0.7,
        top_p=0.8,
        top_k=20,
        min_p=0.0,
        presence_penalty=1.5,
        repetition_penalty=1.0,
        preserve_thinking=False,
    ),
    "Qwen3.6-instruct-reasoning": ModelProfile(
        enable_thinking=False,
        temperature=1.0,
        top_p=0.95,
        top_k=20,
        min_p=0.0,
        presence_penalty=1.5,
        repetition_penalty=1.0,
        preserve_thinking=False,
    ),
}

app = FastAPI(title="Qwen Thinking Proxy")

SKIP_HEADERS = {"host", "content-length", "transfer-encoding"}


def _forward_headers(request: Request) -> dict:
    return {k: v for k, v in request.headers.items() if k.lower() not in SKIP_HEADERS}


def _patch_body(body: dict, virtual_model: str) -> dict:
    profile = MODEL_MAP.get(virtual_model)
    if profile is None:
        return body

    body["model"] = REAL_MODEL

    template_kwargs = {}
    if profile.preserve_thinking:
        template_kwargs["preserve_thinking"] = True
    else:
        template_kwargs["enable_thinking"] = profile.enable_thinking

    body["chat_template_kwargs"] = template_kwargs

    defaults = {
        "temperature": profile.temperature,
        "top_p": profile.top_p,
        "top_k": profile.top_k,
        "min_p": profile.min_p,
        "presence_penalty": profile.presence_penalty,
        "repetition_penalty": profile.repetition_penalty,
    }
    for k, v in defaults.items():
        body.setdefault(k, v)

    return body


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": name,
                "object": "model",
                "created": 1700000000,
                "owned_by": "local",
                "description": f"thinking={'on' if p.enable_thinking else 'off'} | temp={p.temperature} | preserve_thinking={'on' if p.preserve_thinking else 'off'}",
            }
            for name, p in MODEL_MAP.items()
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    raw = await request.body()
    body = json.loads(raw)
    virtual_model = body.get("model", "")
    body = _patch_body(body, virtual_model)
    headers = _forward_headers(request)
    is_stream = body.get("stream", False)

    if is_stream:

        async def _stream():
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=5, read=600, write=120, pool=5),
                    limits=httpx.Limits(max_connections=100),
                ) as client:
                    async with client.stream(
                        "POST",
                        f"{BACKEND_URL}/v1/chat/completions",
                        json=body,
                        headers=headers,
                    ) as resp:
                        async for chunk in resp.aiter_raw():
                            yield chunk
            except BaseException:
                pass

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{BACKEND_URL}/v1/chat/completions",
            json=body,
            headers=headers,
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
)
async def generic_proxy(request: Request, path: str):
    url = f"{BACKEND_URL}/{path}"
    headers = _forward_headers(request)
    body = await request.body()

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
            params=request.query_params,
        )

    return JSONResponse(
        content=resp.json()
        if resp.headers.get("content-type", "").startswith("application/json")
        else {},
        status_code=resp.status_code,
    )


if __name__ == "__main__":
    print("Launching server for llama.cpp/ik_llama.cpp", flush=True)
    uvicorn.run(
        app,
        host=LISTEN_HOST,
        port=LISTEN_PORT,
        log_level="info",
        limit_max_requests=None,
        h11_max_incomplete_event_size=256 * 1024 * 1024,
    )
