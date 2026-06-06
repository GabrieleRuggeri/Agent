import argparse
import asyncio
import os
from typing import AsyncGenerator
import logging


from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import (
    ToolNode,
    tools_condition,  # this is the checker for the if you got a tool back
)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from clients.tavily_client import TavilyClient
from registry.mcp_registry import discover_servers, is_registry_configured
from tools.tool import add, divide, get_today, multiply
from tools.web import make_web_search_tool

load_dotenv()
logger = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-4o", cache=False, temperature=0)
tavily = TavilyClient()
web_search_tool = make_web_search_tool(tavily)


class Agent:

    def __init__(
            self,
            llm,
            web_tool,
            mcp_tools: list, 
            mcp_cleanup=None):

        self.llm = llm
        self.web_tool = web_tool
        self.tools = [add, multiply, divide, get_today, self.web_tool] + mcp_tools
        self.llm_with_tools = self._bind_tools(self.tools)
        self._mcp_cleanup = mcp_cleanup

        system_prompt = (
            "Rispondi alle domande dell'utente, servendoti dei tool a disposizione se necessario. "
            "In caso di richiesta informazioni, fornisci sempre le più aggiornate rispetto ad oggi: recupera la data odierna con il tool 'get_today' e, se devi rispondere a domande su eventi recenti o persone, usa il tool 'web_search' per cercare sul web."
        )
        self.sys_msg = SystemMessage(content=system_prompt)

        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        self.react_graph = builder.compile()

    @classmethod
    async def _connect_http_mcp(cls, url: str) -> tuple[list, object | None]:
        from contextlib import asynccontextmanager

        from mcp.client.streamable_http import streamable_http_client

        @asynccontextmanager
        async def _http_session():
            async with streamable_http_client(url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

        try:
            ctx = _http_session()
            session = await ctx.__aenter__()
            tools = await load_mcp_tools(session)

            async def cleanup():
                await ctx.__aexit__(None, None, None)

            return tools, cleanup
        except Exception as e:
            logger.info(f"Error setting up HTTP MCP client for {url}: {e}")
            return [], None

    @classmethod
    async def _connect_stdio_mcp(cls) -> tuple[list, object | None]:
        server_path = os.environ.get("MCP_SERVER_PATH", "servers/pasta_mcp/pasta_server.py")
        server_params = StdioServerParameters(command="python", args=[server_path])
        stdio_ctx = stdio_client(server_params)
        try:
            read, write = await stdio_ctx.__aenter__()
            session_ctx = ClientSession(read, write)
            session = await session_ctx.__aenter__()
            await session.initialize()
            tools = await load_mcp_tools(session)

            async def cleanup():
                await session_ctx.__aexit__(None, None, None)
                await stdio_ctx.__aexit__(None, None, None)

            return tools, cleanup
        except Exception as e:
            logger.info(f"Error setting up stdio MCP client: {e}")
            return [], None

    @classmethod
    async def _load_mcp_tools(cls) -> tuple[list, object | None]:
        mcp_tools: list = []
        cleanups: list = []

        try:
            if is_registry_configured():
                servers = await asyncio.to_thread(discover_servers)
                for server in servers:
                    if server.transport != "streamable-http":
                        logger.info(
                            "Skipping MCP server %s: unsupported transport %s",
                            server.name,
                            server.transport,
                        )
                        continue

                    tools, cleanup = await cls._connect_http_mcp(server.url)
                    mcp_tools.extend(tools)
                    if cleanup:
                        cleanups.append(cleanup)
            elif os.environ.get("MCP_SERVER_URL"):
                tools, cleanup = await cls._connect_http_mcp(os.environ["MCP_SERVER_URL"])
                mcp_tools.extend(tools)
                if cleanup:
                    cleanups.append(cleanup)
            else:
                tools, cleanup = await cls._connect_stdio_mcp()
                mcp_tools.extend(tools)
                if cleanup:
                    cleanups.append(cleanup)
        except Exception as e:
            logger.exception(f"Error setting up MCP client: {e}")

        if not cleanups:
            return mcp_tools, None

        async def cleanup():
            for fn in cleanups:
                await fn()

        return mcp_tools, cleanup

    @classmethod
    async def create(cls) -> "Agent":
        mcp_tools, cleanup = await cls._load_mcp_tools()
        return cls(llm=llm, web_tool=web_search_tool, mcp_tools=mcp_tools, mcp_cleanup=cleanup)

    def _get_llm(self, model: str = "gpt-4o"):
        try:
            return ChatOpenAI(model=model)
        except Exception as e:
            logger.exception(f"Error initialising LLM: {e}")
            return None

    def _bind_tools(self, tools: list = []):
        return self.llm.bind_tools(tools)  # type: ignore

    def reasoner(self, state: MessagesState):
        return {"messages": [self.llm_with_tools.invoke([self.sys_msg] + state["messages"])]}

    def answer(self, question: str) -> str:
        result = self.react_graph.invoke({"messages": [HumanMessage(content=question)]})  # type: ignore
        return result["messages"][-1].content

    async def stream_answer(self, question: str) -> AsyncGenerator[dict, None]:
        """Stream agent events as structured dicts.

        Yielded shapes:
          {"type": "tool_start", "name": str, "input": dict}
          {"type": "token",      "content": str}
          {"type": "end"}
        """
        async for event in self.react_graph.astream_events(
            {"messages": [HumanMessage(content=question)]},
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_tool_start":
                yield {
                    "type": "tool_start",
                    "name": event.get("name", "unknown_tool"),
                    "input": event["data"].get("input", {}),
                }

            elif kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and chunk.content:
                    yield {"type": "token", "content": chunk.content}

        yield {"type": "end"}

    def _test_run(self):
        messages = [HumanMessage(content="What is 2 times Brad Pitt's age?")]
        messages = self.react_graph.invoke({"messages": messages})  # type: ignore
        print(f"LLM response: {messages['messages'][-1].content}")


async def make_graph():
    a = await Agent.create()
    return a.react_graph


async def main():
    parser = argparse.ArgumentParser(description="Choose response mode: 'full' or 'stream'")
    parser.add_argument("mode", choices=["full", "stream"])
    args = parser.parse_args()
    question = input("Ask me a question: ")

    a = await Agent.create()
    in_answer = False
    if args.mode == "full":
        print(f"Final answer: {a.answer(question)}")
    else:
        async for event in a.stream_answer(question):
            if event["type"] == "tool_start":
                tool_args = ", ".join(f"{k}={v!r}" for k, v in event["input"].items())
                print(f"\n[TOOL: {event['name']}] {tool_args}", flush=True)
                in_answer = False
            elif event["type"] == "token":
                if not in_answer:
                    print()
                    in_answer = True
                print(event["content"], end="", flush=True)
            elif event["type"] == "end":
                print()
    if a._mcp_cleanup:
        await a._mcp_cleanup()


if __name__ == "__main__":
    asyncio.run(main())
