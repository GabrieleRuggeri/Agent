import json
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from main import Agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = await Agent.create()
    yield
    if app.state.agent._mcp_cleanup:
        await app.state.agent._mcp_cleanup()


app = FastAPI(title="AgentAI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND = Path(__file__).parent / "frontend" / "index.html"


@app.get("/")
async def root():
    return HTMLResponse(FRONTEND.read_text())


class ChatRequest(BaseModel):
    message: str


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def generate():
        try:
            async for event in app.state.agent.stream_answer(req.message):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
