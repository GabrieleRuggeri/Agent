# AgenticSystem

A ReAct agent (LangGraph + GPT-4o) with streaming chat, MCP tool integration, and optional PostgreSQL-based MCP discovery in Docker.

---

## Choose how to run

| | **Local** | **Docker Compose** |
|---|---|---|
| **Best for** | Day-to-day development, debugging Python | Full stack as in production, MCP registry demo |
| **Requires** | Python 3.12+, [uv](https://docs.astral.sh/uv/) | Docker Desktop (or Docker Engine + Compose v2) |
| **Database** | None | PostgreSQL 16 Alpine (`postgres:16-alpine`, native ARM64) |
| **MCP connection** | stdio subprocess | HTTP + DB discovery |
| **Start command** | `uv run python server.py` | `docker compose up --build` |
| **Open** | http://localhost:8000 | http://localhost:8000 |

You only need **one** of these paths. They share the same `.env` file for API keys, but use different MCP wiring (see below).

---

## First-time setup (both modes)

Run these steps once, from the project root:

```bash
git clone <your-repo-url> AgenticSystem   # skip if you already have the repo
cd AgenticSystem
cp .env.example .env
```

Edit `.env` and set your API keys (see [minimal `.env` templates](#minimal-env-templates) below).

Then follow **either** [Local setup](#setup-local-development) **or** [Docker setup](#setup-docker-compose).

---

## Setup: Local development

Use this path if you want to run Python directly on your machine — no containers, no database.

### Prerequisites

Install before continuing:

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | https://python.org or `brew install python@3.12` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

Verify:

```bash
python3 --version   # → Python 3.12.x or higher
uv --version        # → uv x.x.x
```

### Step 1 — Configure `.env` for local

Open `.env`. You need **at minimum**:

```env
OPENAI_API_KEY="sk-..."
TAVILY_API_KEY="tvly-..."
```

**Do not set these for normal local dev** (they change how MCP connects):

| Variable | Why leave it unset |
|---|---|
| `POSTGRES_HOST` | If set with `POSTGRES_PASSWORD`, the agent tries DB discovery instead of stdio |
| `MCP_SERVER_URL` | Bypasses stdio; only use if you manually run the MCP server over HTTP |

Optional (defaults are fine):

```env
MCP_SERVER_PATH="servers/pasta_mcp/pasta_server.py"
```

Langfuse tracing (optional):

```env
LANGFUSE_SECRET_KEY="sk-..."
LANGFUSE_PUBLIC_KEY="pk-..."
LANGFUSE_HOST="https://cloud.langfuse.com"
```

### Step 2 — Install dependencies

```bash
uv sync
```

This creates a virtual environment and installs all packages from `pyproject.toml`.

### Step 3 — Start the web UI

```bash
uv run python server.py
```

You should see Uvicorn listening on port 8000. Open **http://localhost:8000** in your browser.

### Step 4 — Verify it works

1. Open http://localhost:8000 — you should see the chat UI.
2. Send a message like *"What is 2 + 2?"* — the agent should reply using built-in tools.
3. Ask *"Give me a carbonara recipe"* — this uses MCP tools from the pasta server (loaded via stdio).

**If pasta tools don't work:** check that `POSTGRES_HOST` is **not** set in your `.env`.

### Other local entry points

```bash
# CLI — full response
uv run python main.py full

# CLI — streaming tokens + tool events
uv run python main.py stream

# LangGraph dev UI (graph inspection)
uv run langgraph dev
# → http://127.0.0.1:2024
```

### What happens at startup (local)

1. `server.py` calls `Agent.create()`.
2. No `POSTGRES_HOST` → agent spawns `pasta_server.py` as a **stdio subprocess**.
3. MCP tools are loaded and bound to GPT-4o.
4. FastAPI serves the UI at `:8000`.

No Docker, no PostgreSQL, no port 8001.

---

## Setup: Docker Compose

Use this path to run the **full stack**: PostgreSQL registry, MCP server (HTTP), and FastAPI — the same way MCP discovery works when services register in a database.

### Prerequisites

| Tool | Notes |
|---|---|
| Docker Desktop | Mac/Windows — includes Compose v2. Linux: Docker Engine + `docker compose` plugin |
| `.env` file | Created in [first-time setup](#first-time-setup-both-modes) |

Verify:

```bash
docker --version        # → Docker 24+
docker compose version  # → Docker Compose v2.x
```

### Step 1 — Configure `.env` for Docker

Open `.env`. You need **API keys plus a database password**:

```env
OPENAI_API_KEY="sk-..."
TAVILY_API_KEY="tvly-..."
POSTGRES_PASSWORD="agentic"
```

`POSTGRES_PASSWORD` can be any string you choose (example uses `agentic`). Compose creates the database with this password on first boot.

**Set by you in `.env`:**

| Variable | Required | Example |
|---|---|---|
| `OPENAI_API_KEY` | Yes | `sk-...` |
| `TAVILY_API_KEY` | Yes | `tvly-...` |
| `POSTGRES_PASSWORD` | Yes | `agentic` |

**Injected automatically by `docker-compose.yml` — do not add to `.env` unless you know why:**

| Variable | Value inside containers |
|---|---|
| `POSTGRES_HOST` | `postgres` |
| `POSTGRES_USER` | `agentic` |
| `POSTGRES_DB` | `agentic` |
| `MCP_PUBLIC_URL` | `http://mcp-server:8001/mcp` (mcp-server only) |

**Do not set for Docker** (unless intentionally overriding):

| Variable | Why |
|---|---|
| `MCP_SERVER_URL` | Docker uses DB discovery; a direct URL bypasses the registry |
| `POSTGRES_HOST` in `.env` | Compose sets this per-service; setting `localhost` in `.env` breaks container networking |

### Step 2 — Start the stack

**Foreground** (logs in terminal — good for first run):

```bash
docker compose up --build
```

**Background** (detached):

```bash
docker compose up --build -d
```

First build takes a few minutes (pulls `postgres:16-alpine`, builds app images). Subsequent starts are ~10–20 seconds.

### Step 3 — Wait for healthy startup

Watch the logs until you see all services ready. Startup order:

```
postgres          →  healthy (pg_isready)
db-migrate        →  exits 0  ("Applying 001_initial..." or "Skipping ... already applied")
mcp-server        →  healthy  (TCP :8001)
fastapi           →  listening on :8000
```

If `db-migrate` fails, see [Troubleshooting](#troubleshooting).

### Step 4 — Verify it works

1. Open **http://localhost:8000** — chat UI loads.
2. Send *"Give me a carbonara recipe"* — agent discovers MCP via PostgreSQL and calls pasta tools.

Optional checks:

```bash
# All services running
docker compose ps

# Migration logs
docker compose logs db-migrate

# MCP server logs
docker compose logs mcp-server

# Confirm MCP server registered (should show one row)
docker compose exec postgres psql -U agentic -d agentic -c "SELECT name, url FROM mcp_servers;"
```

### Services and ports

| Service | Host port | Purpose |
|---|---|---|
| `fastapi` | **8000** | Web UI + `/chat/stream` API |
| `mcp-server` | 8001 | MCP HTTP endpoint (debugging; agent uses internal URL) |
| `postgres` | *(internal)* | MCP registry database |
| `db-migrate` | — | One-shot migration job; exits after applying SQL |

### Stopping and resetting

```bash
# Stop containers (data preserved)
docker compose down

# Stop and wipe database (fresh start)
docker compose down -v
```

If you change `POSTGRES_PASSWORD` after the first run, the old password is stored in the Docker volume. Run `docker compose down -v` to reinitialize, or revert to the original password.

### What happens at startup (Docker)

1. **postgres** starts; healthcheck passes.
2. **db-migrate** runs `migrations/migrate.sh` (piped via stdin on macOS), creates tables, records applied migrations.
3. **mcp-server** registers `name=pasta-expert`, `url=http://mcp-server:8001/mcp` in `mcp_servers`.
4. **fastapi** queries `mcp_servers`, connects to MCP over HTTP, loads tools, serves traffic.

---

## Minimal `.env` templates

Copy the block that matches your mode into `.env` (replace placeholder keys).

**Local only:**

```env
OPENAI_API_KEY="your-openai-api-key"
TAVILY_API_KEY="your-tavily-api-key"
MCP_SERVER_PATH="servers/pasta_mcp/pasta_server.py"
```

**Docker only:**

```env
OPENAI_API_KEY="your-openai-api-key"
TAVILY_API_KEY="your-tavily-api-key"
POSTGRES_PASSWORD="agentic"
```

**Both** (if you switch between local and Docker on the same machine):

```env
OPENAI_API_KEY="your-openai-api-key"
TAVILY_API_KEY="your-tavily-api-key"
POSTGRES_PASSWORD="agentic"
MCP_SERVER_PATH="servers/pasta_mcp/pasta_server.py"
```

For local runs: leave `POSTGRES_HOST` unset. For Docker: compose injects `POSTGRES_HOST=postgres` into containers — your local shell never needs it.

---

## MCP connection modes

The agent picks how to reach MCP servers based on environment variables:

| Priority | Condition | What happens |
|---|---|---|
| 1 | `POSTGRES_HOST` **and** `POSTGRES_PASSWORD` set | Query `mcp_servers` table → connect to each HTTP MCP server |
| 2 | `MCP_SERVER_URL` set (and no registry) | Connect to that single URL |
| 3 | Neither | Spawn `MCP_SERVER_PATH` as stdio subprocess |

| Mode | Used when |
|---|---|
| stdio | Local: `uv run python server.py` |
| DB discovery | Docker: compose sets `POSTGRES_HOST=postgres` on `fastapi` and `mcp-server` |
| Direct URL | Manual testing: `MCP_SERVER_URL=http://localhost:8001/mcp` |

---

## Environment variables (full reference)

| Variable | Local | Docker | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Required | Required | GPT-4o |
| `TAVILY_API_KEY` | Required | Required | Web search |
| `POSTGRES_PASSWORD` | — | Required in `.env` | DB password |
| `POSTGRES_HOST` | Leave unset | Set by compose | Triggers DB discovery when combined with password |
| `POSTGRES_USER` | — | Set by compose | Default `agentic` |
| `POSTGRES_DB` | — | Set by compose | Default `agentic` |
| `MCP_SERVER_PATH` | Optional | Ignored in Docker | stdio script path |
| `MCP_SERVER_URL` | Optional override | Don't set | Direct HTTP MCP URL |
| `LANGFUSE_*` | Optional | Optional | Observability |
| `LANGSMITH_API_KEY` | Optional | Optional | LangGraph dev UI |

See `.env.example` for a commented template.

---

## Troubleshooting

### Setup / startup

| Symptom | Fix |
|---|---|
| `POSTGRES_PASSWORD` / variable not set | Add `POSTGRES_PASSWORD=agentic` to `.env` before `docker compose up` |
| `db-migrate` exits 126 (`Resource deadlock avoided`) | macOS bind-mount issue — already handled in compose; don't change the `cat migrate.sh \| sh` entrypoint |
| `db-migrate` fails / connection refused | Wait for `postgres` healthy; check `docker compose logs postgres db-migrate` |
| `mcp-server`: `No module named 'mcp.server'` | Don't rename Docker workdir to `mcp` — it shadows the pip package (uses `/app/pasta_mcp`) |
| Pasta tools missing in Docker | `docker compose logs mcp-server`; check `mcp_servers` table has a row |
| Pasta tools missing locally | Remove `POSTGRES_HOST` from `.env` |
| Password change ignored | `docker compose down -v` then `docker compose up --build` |
| Orphan `mssql_container` warning | Old SQL Server container — run `docker compose up --remove-orphans` |
| Port 8000 already in use | Stop other process or change port mapping in `docker-compose.yml` |

### Runtime

| Symptom | Note |
|---|---|
| MCP healthcheck uses TCP, not HTTP | `/mcp` returns 406 for plain GET; healthcheck only checks port 8001 is open |
| `fastapi` won't start alone | Use `docker compose up` so dependencies start in order |

---

## Architecture

### Request flow

```
Browser / CLI
    → FastAPI (server.py) :8000
        → Agent (main.py) — LangGraph ReAct loop
            → built-in tools (tools/)
            → MCP tools (servers/pasta_mcp/)
```

### MCP discovery (Docker)

```
mcp-server  ──register──►  PostgreSQL (mcp_servers)  ◄──discover──  fastapi
```

Locally, the agent spawns the MCP server as a stdio subprocess — no database.

---

## Repository layout

```
AgenticSystem/
├── main.py                 # Agent + LangGraph graph
├── server.py               # FastAPI app
├── docker-compose.yml      # postgres + db-migrate + mcp-server + fastapi
├── Dockerfile              # FastAPI image
├── .env.example            # Environment template
├── migrations/             # SQL migrations + migrate.sh
├── registry/               # MCP register / discover (psycopg)
├── frontend/index.html     # Chat UI
├── tools/                  # Built-in agent tools
├── clients/                # Tavily client
└── servers/pasta_mcp/      # MCP server (tools, prompts, resources)
```

---

## Components

### `main.py` — Agent

ReAct loop: `START → reasoner → tools → reasoner → …`

- `Agent.create()` — connects to MCP (stdio, URL, or DB discovery), loads tools
- `Agent.answer()` / `Agent.stream_answer()` — sync and streaming responses
- `make_graph()` — used by `langgraph dev`

### `server.py` — FastAPI

| Route | Description |
|---|---|
| `GET /` | Chat UI |
| `POST /chat/stream` | SSE stream of agent events |

### `registry/mcp_registry.py`

`register_server`, `deregister_server`, `discover_servers` — shared by MCP server and agent.

### `servers/pasta_mcp/`

FastMCP server: `get_carbonara_recipe`, `get_bolognese_recipe`, prompts, `example://pasta_image` resource.

| `MCP_TRANSPORT` | Mode |
|---|---|
| `stdio` (default) | Local subprocess |
| `streamable-http` | Docker HTTP server on :8001 |

### Database tables (Docker)

| Table | Purpose |
|---|---|
| `schema_migrations` | Tracks applied migration versions |
| `mcp_servers` | MCP registry (`name`, `url`, `transport`, timestamps) |

New migrations: add `migrations/002_description.sql` — applied automatically on next `docker compose up`.

---

## Observability

LangGraph runs are traced via [Langfuse](https://langfuse.com). Set `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY` in `.env`.
