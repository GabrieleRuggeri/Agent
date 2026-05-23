# all sorts of imports
from os import system

from langchain_openai import ChatOpenAI
from tools.tool import add, multiply, divide, get_today
from tools.web import make_web_search_tool

from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, SystemMessage

from langgraph.graph import START, StateGraph
from langgraph.prebuilt import tools_condition # this is the checker for the if you got a tool back
from langgraph.prebuilt import ToolNode
from langfuse import get_client
from langfuse.langchain import CallbackHandler

from clients.tavily_client import TavilyClient

from dotenv import load_dotenv
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

    def _test_run(self):
        messages = [HumanMessage(content="What is 2 times Brad Pitt's age?")]
        messages = self.react_graph.invoke({"messages": messages}, config={"callbacks": [self.langfuse_handler]}) # type: ignore
        llm_response = messages["messages"][-1]
        print(f"LLM response: {llm_response.content}")


if __name__ == "__main__":
    agent = Agent()
    answer = agent.answer(input("Ask me a question: "))
    print(f"Answer: {answer}")