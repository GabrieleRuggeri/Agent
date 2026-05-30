# AgenticSystem

A ReAct agent built with LangGraph, powered by GPT-4o, with streaming, MCP tool integration, a FastAPI backend, a minimal chat UI, and Langfuse observability. The system can be run locally or as a Docker Compose stack.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Browser / CLI                     │
└────────────────────┬────────────────────────────────┘
                     │ SSE  /chat/stream
┌────────────────────▼────────────────────────────────┐
│              FastAPI  (server.py)                   │
│  • serves frontend/index.html at GET /              │
│  • streams agent events at POST /chat/stream        │
└────────────────────┬────────────────────────────────┘
                     │ LangGraph react_graph
┌────────────────────▼────────────────────────────────┐
│               Agent  (main.py)                      │
│  ReAct loop: START → reasoner → [tools] → reasoner  │
│  LLM: GPT-4o via ChatOpenAI                         │
└──────┬──────────────────────────┬───────────────────┘
       │ built-in tools           │ MCP tools
┌──────▼──────────┐    ┌──────────▼──────────────────┐
│  tools/         │    │  servers/pasta_mcp/          │
│  • add          │    │  • get_carbonara_recipe      │
│  • multiply     │    │  • get_bolognese_recipe      │
│  • divide       │    │  • how_to_make_pasta (prompt)│
│  • get_today    │    │  • how_to_properly_choose_   │
│  • web_search   │    │    ingredients (prompt)      │
└─────────────────┘    │  • pasta_image (resource)    │
                       └─────────────────────────────-┘
```

The agent connects to the MCP server either via **stdio** (local dev) or **streamable-http** (Docker / remote).

---

## Repository layout

```
AgenticSystem/
├── main.py                        # Agent class + LangGraph graph
├── server.py                      # FastAPI app
├── pyproject.toml                 # Python project & dependencies (uv)
├── langgraph.json                 # LangGraph dev-server config
├── Dockerfile                     # Image for the FastAPI service
├── docker-compose.yml             # Starts MCP server + FastAPI together
├── .env.example                   # Environment variable template
│
├── frontend/
│   └── index.html                 # Single-file chat UI
│
├── tools/
│   ├── tool.py                    # Arithmetic tools + get_today
│   └── web.py                     # Web search tool (Tavily-backed)
│
├── clients/
│   └── tavily_client.py           # Thin wrapper around the Tavily SDK
│
└── servers/
    └── pasta_mcp/
        ├── Dockerfile             # Image for the MCP server
        ├── pasta_server.py        # FastMCP server entry point
        ├── pasta_tools.py         # get_carbonara_recipe, get_bolognese_recipe
        ├── pasta_prompts.py       # how_to_make_pasta, how_to_properly_choose_ingredients
        ├── pasta_resources.py     # pasta_image resource
        └── pasta_img.png          # Sample pasta image served as MCP resource
```

---

## Components

### `main.py` — Agent

The `Agent` class wraps a compiled LangGraph `StateGraph` that implements a ReAct loop:

```
START → reasoner → tools_condition → tools → reasoner → …
```

- **`Agent.create()`** — async factory; connects to the MCP server (HTTP or stdio), loads MCP tools, and returns a ready agent.
- **`Agent.answer(question)`** — synchronous full response.
- **`Agent.stream_answer(question)`** — async generator yielding structured events:
  - `{"type": "tool_start", "name": str, "input": dict}`
  - `{"type": "token", "content": str}`
  - `{"type": "end"}`
- **`make_graph()`** — top-level async function that returns the compiled graph; used by `langgraph.json` for the LangGraph dev UI.

#### MCP connection modes

| `MCP_SERVER_URL` set? | Transport | How |
|---|---|---|
| No | stdio | Spawns `pasta_server.py` as a subprocess via `stdio_client` |
| Yes | streamable-http | Opens a persistent HTTP session via `streamable_http_client`, which yields `(read, write, get_session_id)` and is wrapped with `@asynccontextmanager` to keep the connection alive for the agent's lifetime |

---

### `server.py` — FastAPI

Serves the web UI and the streaming chat endpoint.

| Route | Method | Description |
|---|---|---|
| `/` | GET | Returns `frontend/index.html` |
| `/chat/stream` | POST | Streams agent events as Server-Sent Events |

The `Agent` instance is created once at startup (via FastAPI `lifespan`) and reused across all requests. MCP cleanup is called on shutdown.

---

### `frontend/index.html` — Chat UI

A single-file, zero-dependency web frontend (except `marked.js` from CDN for Markdown rendering).

- Dark theme built with CSS variables; Inter + JetBrains Mono fonts.
- Auto-resizing textarea; `Enter` to send, `Shift+Enter` for newline.
- **Streaming**: tokens are appended as they arrive, with an animated blinking cursor. Markdown is rendered only after the stream ends.
- **Tool visibility**: each tool call appears as a line with an animated pip (purple while running, green when done).
- **Suggestion chips**: clickable example prompts on the welcome screen.
- **Clear button**: resets the conversation view.
- **Error handling**: network and HTTP errors are displayed inline.

---

### `tools/tool.py` — Arithmetic & date tools

| Tool | Signature | Description |
|---|---|---|
| `add` | `(a: int, b: int) → int` | Addition |
| `multiply` | `(a: int, b: int) → int` | Multiplication |
| `divide` | `(a: int, b: int) → float` | Division |
| `get_today` | `() → str` | Returns today's date as `YYYY-MM-DD` |

---

### `tools/web.py` — Web search tool

`make_web_search_tool(client, k=5)` returns a LangChain-compatible tool that calls Tavily and formats up to `k` results as numbered text entries with title, URL, and content snippet.

---

### `clients/tavily_client.py` — Tavily client

Thin wrapper around `tavily.TavilyClient`. Reads `TAVILY_API_KEY` from the environment. Exposes a single `search(query, max_results)` method that returns a list of result dicts.

---

### `servers/pasta_mcp/` — Pasta MCP Server

A [FastMCP](https://github.com/jlowin/fastmcp) server that exposes pasta-domain capabilities over the Model Context Protocol.

**Tools**

| Tool | Returns |
|---|---|
| `get_carbonara_recipe` | Ingredients + step-by-step instructions for Spaghetti Carbonara |
| `get_bolognese_recipe` | Ingredients + step-by-step instructions for Spaghetti Bolognese |

**Prompts**

| Prompt | Description |
|---|---|
| `how_to_make_pasta` | Step-by-step guide for making fresh pasta from scratch |
| `how_to_properly_choose_ingredients` | Guidance on selecting quality ingredients for pasta dishes |

**Resources**

| URI | Description |
|---|---|
| `example://pasta_image` | Sample pasta image (`pasta_img.png`) |

**Transport modes** (controlled by `MCP_TRANSPORT` env var):

- `stdio` (default) — subprocess mode for local dev
- `streamable-http` — HTTP server on `MCP_HOST:MCP_PORT` for Docker / network access

---

## Environment variables

Copy `.env.example` to `.env` and fill in the values:

```
OPENAI_API_KEY=            # Required — GPT-4o
TAVILY_API_KEY=            # Required — web search
LANGFUSE_SECRET_KEY=       # Required — observability
LANGFUSE_PUBLIC_KEY=       # Required — observability
LANGFUSE_HOST=             # Required — e.g. https://cloud.langfuse.com
LANGSMITH_API_KEY=         # Optional — needed for langgraph dev

# Local dev: path to the MCP server script
MCP_SERVER_PATH=servers/pasta_mcp/pasta_server.py

# Docker: URL of the MCP server (overrides MCP_SERVER_PATH when set)
# MCP_SERVER_URL=http://localhost:8001/mcp
```

---

## Running

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose (for containerised mode)

### Local dev — install dependencies

```bash
uv sync
```

### CLI

```bash
# Full response
uv run python main.py full

# Streaming (tokens + tool events printed as they arrive)
uv run python main.py stream
```

### FastAPI + Web UI (local)

```bash
uv run python server.py
# → http://localhost:8000
```

### LangGraph Dev UI

Starts the LangGraph development server with a built-in graph-inspection UI:

```bash
uv run langgraph dev
# → http://127.0.0.1:2024
```

The exposed graph is `my_graph` (defined in `langgraph.json`, points to `main.py:make_graph`). This runs fully locally without containers. The Docker-based `langgraph up` command requires a paid LangSmith account with LangGraph Cloud access.

### Docker Compose

Starts both the MCP server and the FastAPI app:

```bash
docker compose up --build
```

| Service | Port | Description |
|---|---|---|
| `mcp-server` | 8001 | Pasta MCP server (streamable-http transport) |
| `fastapi` | 8000 | FastAPI app + chat UI |

The FastAPI container waits for the MCP server health check before starting. The healthcheck uses a TCP socket connection (not an HTTP GET) because the `/mcp` endpoint requires MCP protocol headers and returns `406` for plain requests. The `MCP_SERVER_URL` env var is set automatically to `http://mcp-server:8001/mcp` inside the compose network.

---

## Observability

All LangGraph runs are traced via [Langfuse](https://langfuse.com). Set `LANGFUSE_HOST` to your self-hosted instance or `https://cloud.langfuse.com` for the managed service.
