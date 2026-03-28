from typing import Annotated , Literal , Optional
import json
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph , START , END
from langgraph.graph.message import add_messages
from schemas.transactions import Transaction
from llm import llm
from schemas.state import State
from agents.query_checker import query_checker
from agents.recommender import recommender
from agents.query_maker import db_query_maker
from agents.query_router import route_query      

from langchain_core.messages import AIMessage

graph_builder = StateGraph(State)

# Add Nodes
graph_builder.add_node('checker', query_checker)
graph_builder.add_node('db_query', db_query_maker)
graph_builder.add_node('recommender', recommender)

# Add Edges
graph_builder.add_edge(START, 'checker')

# Conditional Routing
graph_builder.add_conditional_edges(
    'checker', 
    route_query, 
    {
        'valid': 'db_query',
        'invalid': 'recommender'
    }
)

# End Edges
graph_builder.add_edge('db_query', END)
graph_builder.add_edge('recommender', END)

graph = graph_builder.compile()
def main(voice_text : str):

    for event in graph.stream({'messages': voice_text}):
        for node_name, node_state in event.items():
            
            # 2. Yield the status of the current node
            yield {"status": f"AI completed node: {node_name}"}
            
            # 3. If it's the final node, extract and yield the JSON data
            if node_name == 'db_query':
                final_json = json.loads(node_state['messages'][-1].content)
                print(final_json)
                yield {"status": "Complete", "data": final_json}

if __name__ == "__main__":
    test_input = "I spent 150 rs on an uber ride"
    
    # 4. Because main() uses yield, we must iterate over it with a for-loop
    for update in main(test_input):
        print(update)
# resp = graph.invoke({'messages':'I earned 40 rs from pizza selling'})
# for msg in resp['messages']:
#     msg.pretty_print()
# raw_string =(resp['messages'][-1].content)
# data = json.loads(raw_string)
# print(data['type'])


