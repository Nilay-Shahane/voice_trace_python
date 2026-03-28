from typing import Annotated , Literal , Optional
import json
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph , START , END
from langgraph.graph.message import add_messages

class Transaction(BaseModel):
    type: Literal["income", "expense"]
    amount: float
    currency: str = "INR"
    category: str
    source: Optional[str]
    raw_text: str

class State(TypedDict):
    messages:Annotated[list,add_messages]


import os
from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq

from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o-mini",   # best cheap model
    temperature=0
)
from langchain_core.messages import AIMessage

def db_query_maker(state: State):
    
    msg_content = state['messages'][-1].content
    prompt = f'''Your job is to take the user's message and extract the financial data.
    Ensure it strictly matches the required schema for a MongoDB insertion query.
    Extract the type (income/expense), amount, currency, category, and source.
    '''
    
    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]
    
    db_llm = llm.with_structured_output(Transaction)
    
    parsed_transaction = db_llm.invoke(messages_to_pass)
    
    return {"messages": [AIMessage(content=parsed_transaction.model_dump_json())]}

graph_builder = StateGraph(State)
graph_builder.add_node('db_query',db_query_maker)
graph_builder.add_edge(START , 'db_query')
graph_builder.add_edge('db_query' , END)

graph = graph_builder.compile()
def main(voice_text : str):

    for event in graph.stream({'messages': voice_text}):
        for node_name, node_state in event.items():
            
            # 2. Yield the status of the current node
            yield {"status": f"AI completed node: {node_name}"}
            
            # 3. If it's the final node, extract and yield the JSON data
            if node_name == 'db_query':
                final_json = json.loads(node_state['messages'][-1].content)
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


