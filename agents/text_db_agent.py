from typing import Annotated, Literal, Optional
import json
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from llm import llm
import random
from schemas.state import State
from agents.query_checker import query_checker_sale, query_checker_expense, query_checker_udhar
from agents.recommender import recommender
from agents.query_maker import db_query_maker_sale, expense_query_maker, udhar_query_maker
from agents.query_router import route_query
from agents.query_type_checker import query_type_checker, route_by_type
from langchain_core.messages import AIMessage
from tools.vendor_attributes import get_vendor_attributes
from tools.save_recommendation import save_recommendation
from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()

graph_builder = StateGraph(State)

# --- 1. Add All Nodes ---
graph_builder.add_node('query_type_checker', query_type_checker)
graph_builder.add_node('sale_check', query_checker_sale)
graph_builder.add_node('expense_check', query_checker_expense)
graph_builder.add_node('udhar_check', query_checker_udhar)
graph_builder.add_node('sale_query', db_query_maker_sale)
graph_builder.add_node('expense_query', expense_query_maker)
graph_builder.add_node('udhar_query', udhar_query_maker)
graph_builder.add_node('rec', recommender)

# --- 2. Build the Edges ---
graph_builder.add_edge(START, 'query_type_checker')

graph_builder.add_conditional_edges(
    'query_type_checker',
    route_by_type,
    {
        'sale': 'sale_check',
        'expense': 'expense_check',
        'udhar': 'udhar_check'
    }
)

graph_builder.add_conditional_edges(
    'sale_check',
    route_query,
    {
        'correct': 'sale_query',
        'incorrect': 'rec'
    }
)

graph_builder.add_conditional_edges(
    'expense_check',
    route_query,
    {
        'correct': 'expense_query',
        'incorrect': 'rec'
    }
)

graph_builder.add_conditional_edges(
    'udhar_check',
    route_query,
    {
        'correct': 'udhar_query',
        'incorrect': 'rec'
    }
)

# --- 3. End Edges ---
graph_builder.add_edge('sale_query', END)
graph_builder.add_edge('expense_query', END)
graph_builder.add_edge('udhar_query', END)
graph_builder.add_edge('rec', END)

# Compile the Graph
graph = graph_builder.compile(checkpointer=memory)

try:
    png_bytes = graph.get_graph().draw_mermaid_png()
    with open("langgraph_diagram.png", "wb") as f:
        f.write(png_bytes)
    print("Success: Graph diagram saved as 'langgraph_diagram.png'")
except Exception as e:
    print("Could not generate image. Error:", e)


NODE_DESCRIPTIONS = {
    'query_type_checker': 'Identifying transaction type (sale / expense / udhar)...',
    'sale_check':         'Validating sale details (item, quantity, amount)...',
    'expense_check':      'Validating expense details (type, amount)...',
    'udhar_check':        'Validating udhar details (person, amount, direction)...',
    'sale_query':         'Building sale record for database...',
    'expense_query':      'Building expense record for database...',
    'udhar_query':        'Building udhar record for database...',
    'rec':                'Generating clarification request for missing info...',
}


async def main(voice_text: str, vendor_id: str,num):
    vendor_attributes = await get_vendor_attributes(vendor_id)
    if num==-1:
        num = random.randint(1000, 9999)
        print(num)
    # Use vendor_id as thread_id so each user has isolated memory
    config = {'configurable': {'thread_id': num}}
    print(voice_text)
    async for event in graph.astream({
        'messages': voice_text,
        'recent_msg':voice_text,
        'vendor_id': vendor_id,
        'vendor_attributes': vendor_attributes,
    }, config=config):
        for node_name, node_state in event.items():

            description = NODE_DESCRIPTIONS.get(node_name, f'Processing node: {node_name}...')
            yield {"status": description}

            if node_name in ['sale_query', 'expense_query', 'udhar_query']:
                try:
                    final_json = json.loads(node_state['messages'][-1].content)
                    tx_type = final_json.get('type', node_name)
                    amount = final_json.get('amount', '?')
                    print(f"Transaction ready [{tx_type}] ₹{amount} →", final_json)
                    yield {
                        "status": f"Transaction logged successfully! ({tx_type} · ₹{amount})",
                        "stage": "complete",
                        "data": final_json
                    }
                except json.JSONDecodeError:
                    yield {
                        "status": "Error: AI returned malformed data. Please try again.",
                        "stage": "error",
                        "data": None
                    }

            elif node_name == 'rec':
                raw_content = node_state['messages'][-1].content
                try:
                    suggestions = json.loads(raw_content)
                except json.JSONDecodeError:
                    suggestions = [raw_content]

                print("Clarification needed. Suggestions:", suggestions)

                yield {
                    "status": "Some details are missing. Please clarify.",
                    "stage": "clarification_needed",
                    "data": suggestions,
                    "num":num
                }
                await save_recommendation(vendor_id, suggestions , num)  # ✅ fixed: added await


# ── Local testing only ──────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio

    async def test():
        async for update in main("I spent 150 rs on an uber ride", vendor_id="test_vendor_id"):
            print(update)

    asyncio.run(test())