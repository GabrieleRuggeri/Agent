# AgenticSystem

A ReAct agent built with LangGraph, powered by GPT-4o, with tool use, streaming, and Langfuse observability.

## Architecture

The agent follows a ReAct loop:

```
START → reasoner → [tool call?] → tools → reasoner → ... → END
```

- **`main.py`** — defines the `Agent` class and compiles the `react_graph` exposed to LangGraph
- **`tools/tool.py`** — arithmetic tools (`add`, `multiply`, `divide`) and `get_today`
- **`tools/web.py`** — web search tool backed by Tavily
- **`clients/tavily_client.py`** — thin wrapper around the Tavily SDK

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- API keys for OpenAI, Tavily, and Langfuse

## Setup

1. Clone the repo and install dependencies:
   ```bash
   uv sync
   ```

2. Copy the example env file and fill in your keys:
   ```bash
   cp .env.example .env
   ```

   Required variables:
   ```
   OPENAI_API_KEY=
   TAVILY_API_KEY=
   LANGFUSE_SECRET_KEY=
   LANGFUSE_PUBLIC_KEY=
   LANGFUSE_HOST=
   LANGSMITH_API_KEY=     # optional, needed for langgraph up
   ```

## Running

### CLI

Run the agent interactively from the terminal:

```bash
# Single full response
uv run python main.py full

# Streaming (tokens + tool events printed as they arrive)
uv run python main.py stream
```

### LangGraph Dev UI (local, no Docker)

Start the LangGraph development server with a built-in web UI:

```bash
uv run langgraph dev
```

The UI is served at `http://127.0.0.1:2024` by default. The graph exposed is `my_graph` (defined in `langgraph.json`).

> **Note:** `langgraph dev` runs entirely locally without containers. The Docker-based `langgraph up` command requires a paid LangSmith account with LangGraph Cloud access.

## Observability

All runs are traced via [Langfuse](https://langfuse.com). Set `LANGFUSE_HOST` to your self-hosted instance or `https://cloud.langfuse.com` for the managed service.
