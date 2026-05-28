import argparse
import asyncio
from typing import AsyncGenerator

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from clients.tavily_client import TavilyClient
from tools.tool import add, divide, get_today, multiply
from tools.web import make_web_search_tool

load_dotenv()


class Agent:

    def __init__(self):
        self.llm = self._get_llm()
        self.tavily_client = TavilyClient()
        self.web_search_tool = make_web_search_tool(self.tavily_client)
        self.tools = [add, multiply, divide, get_today, self.web_search_tool]
        self.llm_with_tools = self._bind_tools(self.tools)

        system_prompt = (
            "Rispondi alle domande dell'utente, servendoti dei tool a disposizione se necessario. "
            "In caso di richiesta informazioni, fornisci sempre le più aggiornate rispetto ad oggi."
        )
        self.sys_msg = SystemMessage(content=system_prompt)

        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        self.react_graph = builder.compile()

    def _get_llm(self, model: str = "gpt-4o"):
        try:
            return ChatOpenAI(model=model)
        except Exception as e:
            print(f"Error initialising LLM: {e}")
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


agent = Agent()
react_graph = agent.react_graph


async def main():
    parser = argparse.ArgumentParser(description="Choose response mode: 'full' or 'stream'")
    parser.add_argument("mode", choices=["full", "stream"])
    args = parser.parse_args()
    question = input("Ask me a question: ")

    in_answer = False
    if args.mode == "full":
        print(f"Final answer: {agent.answer(question)}")
    else:
        async for event in agent.stream_answer(question):
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


if __name__ == "__main__":
    asyncio.run(main())
