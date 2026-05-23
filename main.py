# all sorts of imports
import asyncio
from typing import AsyncGenerator

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import (
    ToolNode,
    tools_condition,  # this is the checker for the if you got a tool back
)

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

    def __init__(self):
        self.llm = self._get_llm()
        self.tavily_client = TavilyClient()
        self.web_search_tool = make_web_search_tool(self.tavily_client)
        self.tools = [add, multiply, divide, get_today, self.web_search_tool]
        self.llm_with_tools = self._bind_tools(self.tools)
        self.langfuse_handler = CallbackHandler()

        # System message
        system_prompt = (
            "Rispondi alle domande dell'utente, servendoti dei tool a disposizione se necessario. " 
            "In caso di richiesta informazioni, fornisci sempre le più aggiornate rispetto ad oggi."
        )
        self.sys_msg = SystemMessage(content=system_prompt)

        # Graph
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

    async def stream_answer(self, question: str) -> AsyncGenerator[str, None]:
        """Stream the final answer token by token, skipping tool-call internals."""
        async for event in self.react_graph.astream_events(
            {"messages": [HumanMessage(content=question)]},
            config={"callbacks": [self.langfuse_handler]},
            version="v2",
        ):
            # on_chat_model_stream fires for every LLM chunk
            if event["event"] == "on_chat_model_stream":
                # Skip tool-call chunks (they have no text content)
                chunk = event["data"].get("chunk")
                if chunk and chunk.content:
                    yield chunk.content

    def _test_run(self):
        messages = [HumanMessage(content="What is 2 times Brad Pitt's age?")]
        messages = self.react_graph.invoke({"messages": messages}, config={"callbacks": [self.langfuse_handler]}) # type: ignore
        llm_response = messages["messages"][-1]
        print(f"LLM response: {llm_response.content}")


async def main():
    agent = Agent()
    question = input("Ask me a question: ")
    # stream response
    async for token in agent.stream_answer(question):
        print(token, end="", flush=True)
    print()  # newline after streaming is done

if __name__ == "__main__":
    asyncio.run(main())