# all sorts of imports
from langchain_openai import ChatOpenAI
from tools.tool import add, multiply, divide

from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, SystemMessage

from langgraph.graph import START, StateGraph
from langgraph.prebuilt import tools_condition # this is the checker for the if you got a tool back
from langgraph.prebuilt import ToolNode
from IPython.display import Image, display

from dotenv import load_dotenv
load_dotenv()

class Agent:

    def __init__(self):
        self.llm = self._get_llm()
        self.tools = [add, multiply, divide]
        self.llm_with_tools = self._bind_tools(self.tools)

        # System message
        self.sys_msg = SystemMessage(content="You are a helpful assistant tasked with using search and performing arithmetic on a set of inputs.")

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
    
    def print_graph(self):
        # Display the graph
        display(Image(self.react_graph.get_graph(xray=True).draw_mermaid_png()))

    def _test_run(self):
        messages = [HumanMessage(content="What is 2 times Brad Pitt's age?")]
        messages = self.react_graph.invoke({"messages": messages}) # type: ignore


if __name__ == "__main__":
    agent = Agent()
    agent.print_graph()
    agent._test_run()