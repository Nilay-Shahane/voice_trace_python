from typing import Annotated , Literal , Optional
import json
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph , START , END
from langgraph.graph.message import add_messages
from llm import llm
from schemas.state import State
from agents.query_checker import query_checker_sale,query_checker_expense,query_checker_udhar
from agents.recommender import recommender
from agents.query_maker import db_query_maker_sale, expense_query_maker,udhar_query_maker
from agents.query_router import route_query 
from agents.query_type_checker import query_type_checker ,route_by_type  
from IPython.display import Image, display
from langchain_core.messages import AIMessage

graph_builder = StateGraph(State)

# --- 1. Add All Nodes ---

# Top Level Intent Router
graph_builder.add_node('query_type_checker', query_type_checker)

# Validation Checkers
graph_builder.add_node('sale_check', query_checker_sale)
graph_builder.add_node('expense_check', query_checker_expense)
graph_builder.add_node('udhar_check', query_checker_udhar)

# DB Query Makers (The valid path)
graph_builder.add_node('sale_query', db_query_maker_sale) # Rename to sale_query_maker if you split them
graph_builder.add_node('expense_query', expense_query_maker)
graph_builder.add_node('udhar_query', udhar_query_maker)

# Recommenders (The invalid/missing info path)
graph_builder.add_node('rec', recommender)


# --- 2. Build the Edges ---

# Start Node
graph_builder.add_edge(START, 'query_type_checker')

# First Split: Route to the specific checker based on transaction type
graph_builder.add_conditional_edges(
    'query_type_checker',
    route_by_type,
    {
        'sale': 'sale_check',
        'expense': 'expense_check',
        'udhar': 'udhar_check'
    }
)

# Second Split: Check if the Sale is valid
graph_builder.add_conditional_edges(
    'sale_check',
    route_query,
    {
        'correct': 'sale_query',
        'incorrect': 'rec'
    }
)

# Second Split: Check if the Expense is valid
graph_builder.add_conditional_edges(
    'expense_check',
    route_query,
    {
        'correct': 'expense_query',
        'incorrect': 'rec'
    }
)

# Second Split: Check if the Udhar is valid
graph_builder.add_conditional_edges(
    'udhar_check',
    route_query,
    {
        'correct': 'udhar_query',
        'incorrect': 'rec'
    }
)

# --- 3. End Edges ---
# In LangGraph, "db" and "user" from your drawing represent ending the AI graph 
# and passing control back to your Python backend to either save the DB JSON or speak to the user.

graph_builder.add_edge('sale_query', END)
graph_builder.add_edge('expense_query', END)
graph_builder.add_edge('udhar_query', END)

graph_builder.add_edge('rec', END)

# Compile the Graph
graph = graph_builder.compile()
try:
    # Get the raw bytes of the PNG image
    png_bytes = graph.get_graph().draw_mermaid_png()
    
    # Save those bytes to a file
    with open("langgraph_diagram.png", "wb") as f:
        f.write(png_bytes)
        
    print("Success: Graph diagram saved as 'langgraph_diagram.png' in your current folder.")
    
except Exception as e:
    # Fallback just in case the Mermaid API is unreachable
    print("Could not generate image. Error:", e)
def main(voice_text: str):
    NODE_DESCRIPTIONS = {
        'query_type_checker': ' Identifying transaction type (sale / expense / udhar)...',
        'sale_check':         ' Validating sale details (item, quantity, amount)...',
        'expense_check':      ' Validating expense details (type, amount)...',
        'udhar_check':        ' Validating udhar details (person, amount, direction)...',
        'sale_query':         '  Building sale record for database...',
        'expense_query':      '  Building expense record for database...',
        'udhar_query':        '  Building udhar record for database...',
        'rec':                ' Generating clarification request for missing info...',
    }

    for event in graph.stream({'messages': voice_text}):
        for node_name, node_state in event.items():

            # 1. Yield a human-readable status for each node as it completes
            description = NODE_DESCRIPTIONS.get(node_name, f'⚙️  Processing node: {node_name}...')
            yield {"status": description}

            # 2. Successfully built a DB-ready transaction record
            if node_name in ['sale_query', 'expense_query', 'udhar_query']:
                try:
                    final_json = json.loads(node_state['messages'][-1].content)
                    tx_type = final_json.get('type', node_name)
                    amount  = final_json.get('amount', '?')
                    print(f"Transaction ready [{tx_type}] ₹{amount} →", final_json)
                    yield {
                        "status": f" Transaction logged successfully! ({tx_type} · ₹{amount})",
                        "stage": "complete",
                        "data": final_json
                    }
                except json.JSONDecodeError:
                    yield {
                        "status": " Error: AI returned malformed data. Please try again.",
                        "stage": "error",
                        "data": None
                    }

            # 3. Missing info — ask the user to clarify
            elif node_name == 'rec':
                clarification_msg = node_state['messages'][-1].content
                print(" Clarification needed:", clarification_msg)
                yield {
                    "status": " Some details are missing. Please clarify.",
                    "stage": "clarification_needed",
                    "data": clarification_msg
                }
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


