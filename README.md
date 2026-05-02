# Qwen3.6 Reasoning Toggle Proxy

OpenAI-compatible proxy for Qwen3.6 models with dynamic configuration of thinking (reasoning) capabilities.
Toggle or disable Qwen's thinking dynamically by just changing the selected model WITHOUT changing the backend configuration.

## Features

- Exposes 4 virtual models with different reasoning configurations
- OpenAI API compatible (`/v1/chat/completions`, `/v1/models`)
- Compatible with Open-WebUI, OpenCode, Codex CLI, Continue, etc..
- Streaming support (SSE)
- Environment variable configuration

## Virtual Models

| Model | Thinking | Temperature | Use Case |
|-------|----------|-------------|----------|
| `qwen3.6-thinking` | On | 1.0 | General reasoning |
| `qwen3.6-thinking-coding` | On | 0.6 | Code generation |
| `qwen3.6-instruct` | Off | 0.7 | Standard instruct |
| `qwen3.6-instruct-reasoning` | Off | 1.0 | Reasoning without thought blocks |

As of May 2nd, 2026, I discovered that Qwen3.6 ships with a new `preserve_thinking` kwarg, which preserves the reasoning traces of the previous conversations. It was shown to increase the model's capacities on long reasoning and coding sessions so I enabled it on the "Qwen3.6-thinking-coding" virtual model.

<!-- Sampling parameters were chosen based on the Qwen3.6-27B official Huggingface repo. -->

## Installation

```bash
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_URL` | `http://localhost:8080` | llama.cpp/llama-server URL |
| `REAL_MODEL` | `qwen3.6-27b` | Actual model name on backend |
| `LISTEN_HOST` | `0.0.0.0` | Proxy listen host |
| `LISTEN_PORT` | `9999` | Proxy listen port |

## Usage
```bash
uv sync
```


```bash
python proxy.py
```

OR with uvicorn directly:

```bash
uvicorn proxy:app --host 0.0.0.0 --port 9999
```

## API Usage

```bash
curl http://localhost:9999/v1/models

curl http://localhost:9999/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.6-27b-thinking",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

## Future developments

This proxy is only compatible with OpenAI APIs, I might extend it to support other API formats (Anthropics, Responses) in the future.

## Transparency

Built with the assistance of Qwen3.6-27B.

Idea, architecture, debugging made by myself.

## License

MIT
