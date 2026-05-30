# all sorts of imports
import argparse
import asyncio
import os
from typing import AsyncGenerator


from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import (
    ToolNode,
    tools_condition,  # this is the checker for the if you got a tool back
)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from clients.tavily_client import TavilyClient
from tools.tool import add, divide, get_today, multiply
from tools.web import make_web_search_tool

load_dotenv()

langfuse = get_client()

# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")


class Agent:

    def __init__(self, mcp_tools: list):
        self.llm = self._get_llm()
        self.tavily_client = TavilyClient()
        self.web_search_tool = make_web_search_tool(self.tavily_client)
        self.tools = [add, multiply, divide, get_today, self.web_search_tool] + mcp_tools
        self.llm_with_tools = self._bind_tools(self.tools)
        self.langfuse_handler = CallbackHandler()

        # System message
        system_prompt = (
            "Rispondi alle domande dell'utente, servendoti dei tool a disposizione se necessario. "
            "In caso di richiesta informazioni, fornisci sempre le più aggiornate rispetto ad oggi."
        )
        self.sys_msg = SystemMessage(content=system_prompt)

        # Graph
        builder = StateGraph(MessagesState)

        # Add nodes
        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", ToolNode(self.tools)) # for the tools
        # Add edges
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges(
            "reasoner",
            # If the latest message (result) from node reasoner is a tool call -> tools_condition routes to tools
            # If the latest message (result) from node reasoner is a not a tool call -> tools_condition routes to END
            tools_condition,
        )
        builder.add_edge("tools", "reasoner")
        self.react_graph = builder.compile()

    @classmethod
    async def create(cls) -> "Agent":
        server_path = os.environ.get("MCP_SERVER_PATH", "servers/pasta_mcp/pasta_server.py")
        server_params = StdioServerParameters(command="python", args=[server_path])
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                mcp_tools = await load_mcp_tools(session)
        return cls(mcp_tools=mcp_tools)

    def _get_llm(self, model: str = "gpt-4o"):
        try:
            llm = ChatOpenAI(model=model)
        except Exception as e:
            print(f"Error occurred while initializing LLM: {e}")
            llm = None
        return llm
    
    def _bind_tools(self, tools: list = []):
        llm_with_tools = self.llm.bind_tools(tools) # type: ignore
        return llm_with_tools
    
    def reasoner(self, state: MessagesState):
        return {"messages": [self.llm_with_tools.invoke([self.sys_msg] + state["messages"])]}
    
    def answer(self, question: str) -> str:
        result = self.react_graph.invoke({"messages": [HumanMessage(content=question)]}, config={"callbacks": [self.langfuse_handler]}) # type: ignore
        return result["messages"][-1].content

    async def stream_answer(self, question: str) -> AsyncGenerator[dict, None]:
        """Stream agent events as structured dicts.

        Yielded event shapes:
          {"type": "tool_start", "name": str, "input": dict}
          {"type": "token",      "content": str}
          {"type": "end"}
        """
        async for event in self.react_graph.astream_events(
            {"messages": [HumanMessage(content=question)]},
            config={"callbacks": [self.langfuse_handler]},
            version="v2",
        ):
            kind = event["event"]

            # Tool invocation — emit name + input args
            if kind == "on_tool_start":
                yield {
                    "type": "tool_start",
                    "name": event.get("name", "unknown_tool"),
                    "input": event["data"].get("input", {}),
                }

            # LLM token — only forward text chunks (skip tool-call deltas)
            elif kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and chunk.content:
                    yield {"type": "token", "content": chunk.content}

        yield {"type": "end"}

    def _test_run(self):
        messages = [HumanMessage(content="What is 2 times Brad Pitt's age?")]
        messages = self.react_graph.invoke({"messages": messages}, config={"callbacks": [self.langfuse_handler]}) # type: ignore
        llm_response = messages["messages"][-1]
        print(f"LLM response: {llm_response.content}")


async def main():
    response_mode = argparse.ArgumentParser(description="Choose response mode: 'full' or 'stream'")
    response_mode.add_argument("mode", choices=["full", "stream"], help="Response mode")
    args = response_mode.parse_args()
    agent = await Agent.create()
    question = input("Ask me a question: ")

    in_answer = False  # track when we switch from tool events to answer tokens
    if args.mode == "full":
        answer = agent.answer(question)
        print(f"Final answer: {answer}")
    else:
        async for event in agent.stream_answer(question):
            if event["type"] == "tool_start":
                # Print a separator before the first tool call if needed
                name = event["name"]
                tool_args = ", ".join(f"{k}={v!r}" for k, v in event["input"].items())
                print(f"\n[TOOL: {name}] {tool_args}", flush=True)
                in_answer = False

            elif event["type"] == "token":
                if not in_answer:
                    # First answer token — add a blank line to separate from tool logs
                    print()
                    in_answer = True
                print(event["content"], end="", flush=True)

            elif event["type"] == "end":
                print()  # final newline

agent = asyncio.get_event_loop().run_until_complete(Agent.create())
react_graph = agent.react_graph

if __name__ == "__main__":
    asyncio.run(main())