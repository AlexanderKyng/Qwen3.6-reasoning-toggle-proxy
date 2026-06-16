#!/usr/bin/env python3
"""
qwen-thinking-proxy
Exposes virtual OpenAI-compatible models for vLLM:
  - Qwen3.6-thinking        → chat_template_kwargs: {enable_thinking: true}
  - Qwen3.6-instruct        → chat_template_kwargs: {enable_thinking: false}

Listens on http://localhost:9999
"""

import json
from dataclasses import dataclass

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# ── Config ──────────────────────────────────────────────────────────────────
BACKEND_URL = "http://localhost:8080"  # Your vLLM server address
REAL_MODEL = "qwen3.6-27b"  # Actual model identifier loaded by vLLM
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 9999


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
}

# ────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Qwen Thinking Proxy")

SKIP_HEADERS = {"host", "content-length", "transfer-encoding"}


def _forward_headers(request: Request) -> dict:
    return {k: v for k, v in request.headers.items() if k.lower() not in SKIP_HEADERS}


def _patch_body(body: dict, virtual_model: str) -> dict:
    body["model"] = REAL_MODEL

    profile = MODEL_MAP.get(virtual_model)
    if profile is None:
        return body

    template_kwargs = {}
    if profile.preserve_thinking:
        template_kwargs["preserve_thinking"] = True
    else:
        template_kwargs["enable_thinking"] = profile.enable_thinking

    body["chat_template_kwargs"] = template_kwargs

    std_defaults = {
        "temperature": profile.temperature,
        "top_p": profile.top_p,
        "presence_penalty": profile.presence_penalty,
    }
    for k, v in std_defaults.items():
        body.setdefault(k, v)

    extra_defaults = {
        "top_k": profile.top_k,
        "min_p": profile.min_p,
        "repetition_penalty": profile.repetition_penalty,
    }
    extra = body.setdefault("extra_body", {})
    for k, v in extra_defaults.items():
        extra.setdefault(k, v)

    return body


# ── /v1/models ───────────────────────────────────────────────────────────────
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
                "description": f"thinking={'on' if p.enable_thinking else 'off'} | temp={p.temperature}",
            }
            for name, p in MODEL_MAP.items()
        ],
    }


# ── /v1/chat/completions ─────────────────────────────────────────────────────
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    raw = await request.body()
    body = json.loads(raw)
    virtual_model = body.get("model", "")

    body = _patch_body(body, virtual_model)
    headers = _forward_headers(request)
    is_stream = body.get("stream", False)

    if is_stream:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=600, write=120, pool=5)
        )
        try:
            req = client.build_request(
                "POST",
                f"{BACKEND_URL}/v1/chat/completions",
                json=body,
                headers=headers,
            )
            resp = await client.send(req, stream=True)

            if resp.status_code != 200:
                await resp.aread()
                print(
                    f"[Proxy Error] vLLM rejected with status {resp.status_code}: {resp.text}"
                )
                await client.aclose()
                return JSONResponse(
                    content={"error": resp.text}, status_code=resp.status_code
                )

            async def _stream_generator():
                try:
                    async for chunk in resp.aiter_raw():
                        yield chunk
                finally:
                    await resp.aclose()
                    await client.aclose()

            return StreamingResponse(
                _stream_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
            )
        except Exception as e:
            print(f"[Proxy Exception] Failed to initialize stream: {e}")
            await client.aclose()
            return JSONResponse(
                content={"error": "Proxy streaming initialization error"},
                status_code=500,
            )

    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{BACKEND_URL}/v1/chat/completions",
            json=body,
            headers=headers,
        )

    if resp.status_code != 200:
        error_text = await resp.aread()

        async def _err_gen():
            yield f"data: {json.dumps({'error': f'vLLM {resp.status_code}: {error_text.decode()}'})}\n\n"

        await resp.aclose()
        await client.aclose()
        return StreamingResponse(_err_gen(), media_type="text/event-stream")

    return JSONResponse(
        content=resp.json() if resp.status_code == 200 else {"error": resp.text},
        status_code=resp.status_code,
    )


# ── Generic Catch-All Proxy ──────────────────────────────────────────────────
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

    try:
        content = resp.json()
    except Exception:
        content = {}

    return JSONResponse(
        content=content,
        status_code=resp.status_code,
    )


if __name__ == "__main__":
    print("Launching server for vLLM/SGLang", flush=True)
    uvicorn.run(
        app,
        host=LISTEN_HOST,
        port=LISTEN_PORT,
        log_level="info",
        limit_max_requests=None,
    )
