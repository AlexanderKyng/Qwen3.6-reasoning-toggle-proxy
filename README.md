# Qwen3.5 Reasoning Toggle Proxy

OpenAI-compatible proxy for Qwen3.5 models with dynamic configuration of thinking (reasoning) capabilities.
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
| `qwen3.5-27b-thinking` | On | 1.0 | General reasoning |
| `qwen3.5-27b-thinking-coding` | On | 0.6 | Code generation |
| `qwen3.5-27b-instruct` | Off | 0.7 | Standard instruct |
| `qwen3.5-27b-instruct-reasoning` | Off | 1.0 | Reasoning without thought blocks |

<!-- Sampling parameters were chosen based on the Qwen3.5-27B official Huggingface repo. -->

## Installation

```bash
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_URL` | `http://localhost:8088` | llama.cpp/llama-server URL |
| `REAL_MODEL` | `qwen3.5-27b` | Actual model name on backend |
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
    "model": "qwen3.5-27b-thinking",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

## Future developments

This proxy is only compatible with OpenAI APIs, I might extend it to support other API formats (Anthropics, Responses) in the future.

## Transparency

Built with the assistance of Qwen3.5-27B.

Idea, architecture, debugging made by myself.

## License

MIT