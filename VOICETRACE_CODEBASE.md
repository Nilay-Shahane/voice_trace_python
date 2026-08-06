# agents\__init__.py

```py

```

# agents\next_day_agent.py

```py
# agents/next_day_agent.py

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from schemas.vendor import VendorState
from llm import llm
from datetime import datetime, timedelta
from bson import ObjectId
from db import get_db
from tools.lang import get_vendor_language


# ─────────────────────────────────────────
# DB FETCH
# ─────────────────────────────────────────
async def fetch_vendor_daily_records(vendor_id: str, days: int = 7) -> list:
    db = get_db()

    since_date = datetime.utcnow() - timedelta(days=days)

    query = {
        "vendorId": ObjectId(vendor_id),
        "date": {"$gte": since_date}
    }

    print(f"📦 Fetching daily records for vendor {vendor_id} (last {days} days)...")

    cursor = db["dailyrecords"].find(query).sort("date", -1)
    records = await cursor.to_list(length=days)

    print(f"✅ Found {len(records)} records")

    return records


# ─────────────────────────────────────────
# SERIALIZER
# ─────────────────────────────────────────
def serialize_records(records: list) -> list:
    clean = []
    for doc in records:
        clean.append({
            k: (str(v) if isinstance(v, ObjectId) else
                v.isoformat() if isinstance(v, datetime) else v)
            for k, v in doc.items()
        })
    return clean


# ─────────────────────────────────────────
# NODES
# ─────────────────────────────────────────

async def fetch_data_node(state: VendorState) -> VendorState:
    print(f"[fetch_data] Loading data for vendor {state['vendor_id']} ...")
    raw = await fetch_vendor_daily_records(state["vendor_id"], days=7)
    lang = await get_vendor_language(state["vendor_id"])
    return {**state, "raw_data": serialize_records(raw), "lang": lang}


def agent_node(state: VendorState) -> VendorState:
    print("[agent] Analysing data and generating suggestions ...")

    lang = state["lang"]

    day_summaries = []
    for day in state["raw_data"]:
        sold   = ", ".join(f"{i['item']}×{i['quantity']}" for i in day.get("itemsSold",  []))
        unsold = ", ".join(f"{i['item']}×{i['quantity']}" for i in day.get("unsoldItems", []))
        wasted = ", ".join(f"{i['item']}×{i['quantity']}" for i in day.get("wastedItems", []))
        day_summaries.append(
            f"Date: {day['date']}\n"
            f"  Sold    : {sold   or 'none'}\n"
            f"  Unsold  : {unsold or 'none'}\n"
            f"  Wasted  : {wasted or 'none'}"
        )

    history_text = "\n\n".join(day_summaries)

    prompt = f"""
You are a smart business assistant helping a small food vendor plan stock for tomorrow.

Below is the vendor's sales history for the past few days (sold / unsold / wasted items):

{history_text}

Task:
1. Look at sell-through trends (what sells fast vs. what stays unsold or gets wasted).
2. Generate a "Next-Day Stock Suggestion" — one line per item.
   Format: "<item>: prepare <quantity> units — <short reason>"
   - Increase quantity for fast-selling items.
   - Decrease or skip items that are repeatedly unsold or wasted.
   - Keep language simple so a street-vendor can understand.
   - Generate all suggestions in the following language: {lang}

Return ONLY the suggestion lines, nothing else.
""".strip()

    response = llm.invoke(prompt)
    suggestions_text = response.content.strip()
    suggestions = [line.strip() for line in suggestions_text.splitlines() if line.strip()]

    return {**state, "analysis": suggestions_text, "suggestions": suggestions}


def output_node(state: VendorState) -> VendorState:
    print("\n" + "═" * 55)
    print("   📦  NEXT-DAY STOCK SUGGESTIONS")
    print("═" * 55)
    for line in state["suggestions"]:
        print(f"  • {line}")
    print("═" * 55 + "\n")
    return state


# ─────────────────────────────────────────
# GRAPH
# ─────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(VendorState)

    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("agent",      agent_node)
    graph.add_node("output",     output_node)

    graph.set_entry_point("fetch_data")
    graph.add_edge("fetch_data", "agent")
    graph.add_edge("agent",      "output")
    graph.add_edge("output",     END)

    return graph.compile()


# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────

if __name__ == "__main__":
    app = build_graph()

    initial_state: VendorState = {
        "vendor_id":   "69c7ee1bb5546e91df1818eb",
        "raw_data":    [],
        "analysis":    "",
        "suggestions": [],
        "lang":        "",
    }

    final_state = asyncio.run(app.ainvoke(initial_state))
```

# agents\query_checker.py

```py
import json
from schemas.check import Check
from schemas.state import State
from llm import llm
from langchain_core.messages import AIMessage


def query_checker_sale(state: State):
    msg_content = state['recent_msg']
    print("Evaluating sale:", msg_content)

    prompt = f'''You are a strict data validation agent for a transaction logging system.

Your ONLY job is to determine whether the user's message contains enough information to log a SALE transaction.
Do NOT extract values. Do NOT make assumptions. Only evaluate completeness.

Required fields for a valid sale:
1. type     → Must clearly indicate a sale (sold, selling, sale, etc.)
2. amount   → A monetary value must be explicitly stated
3. item     → The product or service being sold must be named
4. quantity → Required ONLY for countable physical goods (NOT required for services)

Rules:
- Do NOT infer missing values from context
- Quantity is NOT required for services (e.g., haircut, repair, consultation)
- If a field is ambiguous or absent, mark it as missing

Examples:
- "I sold 2 pizzas for 80 rupees"          → {{ "valid": true,  "missing": [] }}
- "I gave a haircut for 150 rupees"          → {{ "valid": true,  "missing": [] }}
- "I sold pizzas for 80 rupees"              → {{ "valid": false, "missing": ["quantity"] }}
- "I sold 2 pizzas"                          → {{ "valid": false, "missing": ["amount"] }}
- "I sold something for 100 rupees"          → {{ "valid": false, "missing": ["item"] }}
- "I made a sale today"                      → {{ "valid": false, "missing": ["item", "amount"] }}

User Message: "{msg_content}"
'''

    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]

    check_llm = llm.with_structured_output(Check)
    parsed_check = check_llm.invoke(messages_to_pass)

    return {"messages": [AIMessage(content=parsed_check.model_dump_json())]}


def query_checker_expense(state: State):
    msg_content = state['original_input']
    print("Evaluating expense:", msg_content)

    prompt = f'''You are a strict data validation agent for a transaction logging system.

Your ONLY job is to determine whether the user's message contains enough information to log an EXPENSE transaction.
Do NOT extract values. Do NOT make assumptions. Only evaluate completeness.

Required fields for a valid expense:
1. type        → Must clearly indicate spending money (spent, paid, bought, etc.)
2. amount      → A monetary value must be explicitly stated
3. expenseType → What the money was spent on must be named (e.g., transport, rent, supplies, food)

Rules:
- Do NOT infer missing values from context
- If a field is ambiguous or absent, mark it as missing

Examples:
- "I spent 150 on an auto rickshaw"              → {{ "valid": true,  "missing": [] }}
- "Paid 5000 for the shop rent"                  → {{ "valid": true,  "missing": [] }}
- "Bought 200 rupees worth of cleaning supplies"  → {{ "valid": true,  "missing": [] }}
- "I spent 500 today"                            → {{ "valid": false, "missing": ["expenseType"] }}
- "I paid the electricity bill"                  → {{ "valid": false, "missing": ["amount"] }}
- "I paid some money"                            → {{ "valid": false, "missing": ["amount", "expenseType"] }}

User Message: "{msg_content}"
'''

    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]

    check_llm = llm.with_structured_output(Check)
    parsed_check = check_llm.invoke(messages_to_pass)

    return {"messages": [AIMessage(content=parsed_check.model_dump_json())]}


def query_checker_udhar(state: State):
    msg_content = state['original_input']
    print("Evaluating udhar:", msg_content)

    prompt = f'''You are a strict data validation agent for a transaction logging system.

Your ONLY job is to determine whether the user's message contains enough information to log an UDHAR (credit/debt) transaction.
Do NOT extract values. Do NOT make assumptions. Only evaluate completeness.

Required fields for a valid udhar entry:
1. type       → Must clearly indicate whether the user is GIVING udhar (lending) or RECEIVING udhar (borrowing / being repaid)
2. amount     → A monetary value must be explicitly stated
3. personName → The name of the specific person involved must be mentioned

Rules:
- Do NOT infer missing values from context
- Generic references like "a customer" or "someone" are NOT valid personNames
- If a field is ambiguous or absent, mark it as missing

Examples:
- "I gave 500 udhar to Rahul"                    → {{ "valid": true,  "missing": [] }}
- "Suresh took 1000 rupees from me on credit"     → {{ "valid": true,  "missing": [] }}
- "Amit paid back the 200 rupees he owed me"      → {{ "valid": true,  "missing": [] }}
- "I gave 500 udhar today"                        → {{ "valid": false, "missing": ["personName"] }}
- "Rahul took some money on credit"               → {{ "valid": false, "missing": ["amount"] }}
- "I gave udhar to Amit"                          → {{ "valid": false, "missing": ["amount"] }}
- "Someone owes me money"                         → {{ "valid": false, "missing": ["amount", "personName"] }}

User Message: "{msg_content}"
'''

    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]

    check_llm = llm.with_structured_output(Check)
    parsed_check = check_llm.invoke(messages_to_pass)

    return {"messages": [AIMessage(content=parsed_check.model_dump_json())]}
```

# agents\query_maker.py

```py
import json
from typing import Annotated , Literal , Optional
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph , START , END
from langgraph.graph.message import add_messages
from schemas.check import Check
from schemas.state import State
from llm import llm
from langchain_core.messages import AIMessage
from schemas.transactions import SaleTransaction,ExpenseTransaction, UdharTransaction

def db_query_maker_sale(state: State):
    msg_content = state['recent_msg']
    
    prompt = f'''Your job is to act as a financial data extraction engine.
    Take the user's voice transcript and extract the data to strictly match the provided schema for a MongoDB insertion.
    
    Rules for Extraction:
    1. type: You MUST classify the transaction as EXACTLY one of: ["sale", "expense", "udhar_given", "udhar_received", "waste", "unsold", "correction"].
       - If they earned money selling a product, it's a "sale".
       - If they bought supplies, paid rent, or paid for transport, it's an "expense".
    2. amount: Extract the total monetary value (float).
    3. item & quantity: If it is a "sale", "waste", or "unsold" event, you MUST try to extract the item name and the quantity. 
       - CRITICAL: Normalize the 'item' name to be SINGULAR (e.g., "pizzas" becomes "pizza", "apples" becomes "apple").
    4. pricePerUnit: If both 'amount' and 'quantity' are successfully extracted, calculate and output this field as (amount / quantity).
    5. Optional Fields: Extract personName (for udhar), expenseType, or a general note ONLY if explicitly mentioned.
    6. flags: If the user mentions a sale but doesn't specify how many they sold, add "missing_quantity" to the flags. If they use words like "around", "roughly", or "maybe", add "approximation_used".
    7. confidence: Assign a float between 0.0 and 1.0 representing how clear and complete the user's original message was.
    8. transcript: Pass the exact user message into the transcript field.
    '''
    
    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]
    
    print('I AM SALE QUERY MAKER')
    db_llm = llm.with_structured_output(SaleTransaction)
    parsed_transaction = db_llm.invoke(messages_to_pass)
    
    return {"messages": [AIMessage(content=parsed_transaction.model_dump_json())]}

def expense_query_maker(state: State):
    msg_content = state['messages'][0].content 
    
    prompt = f'''Your job is to act as a financial data extraction engine for EXPENSES.
    Take the user's voice transcript and extract the data to strictly match the ExpenseTransaction schema for a MongoDB insertion.
    
    Rules for Extraction:
    1. type: You MUST classify this as "expense".
    2. amount: Extract the total monetary value (float).
    3. expenseType: Identify the category of the expense (e.g., "transport", "rent", "supplies", "food", "utilities"). Keep it to a single, descriptive word if possible.
    4. note: Extract any additional context or reason for the expense ONLY if explicitly mentioned.
    5. flags: If the user uses words like "around", "roughly", or "maybe", add "approximation_used". If the exact nature of the expense is unclear, add "ambiguous_expense".
    6. confidence: Assign a float between 0.0 and 1.0 representing how clear the user's message was.
    7. transcript: Pass the exact user message into the transcript field.
    '''
    
    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]
    
    print('I AM EXPENSE QUERY MAKER')
    db_llm = llm.with_structured_output(ExpenseTransaction)
    parsed_transaction = db_llm.invoke(messages_to_pass)
    
    # Dump by alias to ensure 'type' is mapped correctly for MongoDB
    return {"messages": [AIMessage(content=parsed_transaction.model_dump_json(by_alias=True))]}

def udhar_query_maker(state: State):
    msg_content = state['messages'][0].content 
    
    prompt = f'''Your job is to act as a financial data extraction engine for UDHAR (Credit/Debt).
    Take the user's voice transcript and extract the data to strictly match the UdharTransaction schema for a MongoDB insertion.
    
    Rules for Extraction:
    1. type: You MUST accurately determine the direction of the credit. 
       - Use "udhar_given" if the user lent money or gave goods on credit.
       - Use "udhar_received" if the user borrowed money or took goods on credit.
    2. amount: Extract the total monetary value (float).
    3. personName: Extract the exact name of the person involved in this transaction. 
    4. flags: If the user uses words like "around" or "roughly", add "approximation_used". If they mention a relationship instead of a name (e.g., "my brother", "that guy") or the name is entirely missing, add "ambiguous_person".
    5. confidence: Assign a float between 0.0 and 1.0 representing how clear the user's message was.
    6. transcript: Pass the exact user message into the transcript field.
    '''
    
    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]
    
    print('I AM UDHAR QUERY MAKER')
    db_llm = llm.with_structured_output(UdharTransaction)
    parsed_transaction = db_llm.invoke(messages_to_pass)
    
    return {"messages": [AIMessage(content=parsed_transaction.model_dump_json(by_alias=True))]}
```

# agents\query_router.py

```py
import json
from typing import Annotated , Literal , Optional
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph , START , END
from langgraph.graph.message import add_messages
from schemas.check import Check
from schemas.state import State
from llm import llm
from langchain_core.messages import AIMessage

def route_query(state: State) -> str:
    # Read the output from the checker node
    last_message = state['messages'][-1].content
    try:
        check_data = json.loads(last_message)
        # Assuming your Check schema has a boolean 'flag' attribute
        print(check_data.get('missing'))
        if check_data.get('flag') == True:
            return 'correct'
        else:
            return 'incorrect'
    except json.JSONDecodeError:
        return 'invalid'
```

# agents\query_type_checker.py

```py
import json
from schemas.transaction_type import TransactionType
from schemas.state import State
from llm import llm
from langchain_core.messages import AIMessage


def query_type_checker(state: State):
    msg_content = state['messages'][0].content

    prompt = f'''You are a transaction classification agent for a small business POS system.
Your ONLY job is to classify the user's message into exactly one of three transaction types.

Transaction Types:
- sale     → The vendor SOLD something to a customer (keywords: sold, selling, sale, becha, diya)
- expense  → The vendor SPENT money on something (keywords: spent, paid, bought, kharcha, expense)
- udhar    → A credit/debt transaction, either given or received (keywords: udhar, credit, borrowed, lent, udhaar)

Rules:
- Classify based on intent, not just keywords
- If ambiguous, pick the closest match
- Never return anything other than: sale, expense, or udhar

Examples:
- "I sold 2 pizzas for 80 rs"           → sale
- "I spent 150 on an auto"              → expense
- "Paid shop rent 5000"                 → expense
- "Rahul took 500 on udhar"             → udhar
- "I gave 200 to Suresh on credit"      → udhar
- "Becha 3 samose 30 mein"              → sale

User Message: "{msg_content}"
'''

    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]

    check_llm = llm.with_structured_output(TransactionType)
    parsed_check = check_llm.invoke(messages_to_pass)

    print(f"Transaction type detected: {parsed_check.model_dump_json()}")
    return {
        "messages": [AIMessage(content=parsed_check.model_dump_json())],
        "original_input": msg_content,  # set once here, never overwritten
    }


def route_by_type(state: State) -> str:
    last_message = state['messages'][-1].content

    try:
        type_data = json.loads(last_message)
        intent = type_data.get('transaction_type', type_data.get('type', '')).lower().strip()

        if intent in ['sale', 'expense', 'udhar']:
            print(f"Routing to: {intent}")
            return intent

        print(f"WARNING: Unexpected transaction type '{intent}', defaulting to 'sale'")
        return 'sale'

    except json.JSONDecodeError:
        print("ERROR: Could not decode JSON in route_by_type. Raw content:", last_message)
        return 'sale'
```

# agents\recommender.py

```py
import json
from schemas.state import State
from llm import llm
from langchain_core.messages import AIMessage
from tools.lang import get_vendor_language

async def recommender(state: State):
    print("--- EXECUTING RECOMMENDER NODE ---")

    # 1. Get the original user message
    msg_content = state["messages"][0].content

    # 2. Parse the JSON string from query_checker to get missing fields
    last_msg_content = state["messages"][-1].content
    try:
        parsed = json.loads(last_msg_content)
        missing_fields = parsed.get("missing", ["unknown_field"])
    except (json.JSONDecodeError, AttributeError):
        missing_fields = ["unknown_field"]

    print("Missing fields:", missing_fields)

    # 3. Pull vendor's real item catalog from state (set by get_vendor_attributes)
    vendor_attributes = state.get("vendor_attributes", {})
    item_catalog = vendor_attributes.get("itemCatalog", [])
    vendor_name = vendor_attributes.get("vendorName", "the vendor")

    # 4. Serialize catalog and missing fields for injection into prompt
    item_catalog_str = json.dumps(item_catalog, indent=2) if item_catalog else "No catalog available."
    missing_fields_str = ", ".join(missing_fields)
    lang = await get_vendor_language(state["vendor_id"])
    print(lang)
    # 5. System prompt with all variables properly injected
    system_prompt = f"""You are a retail transaction assistant embedded in a POS system.
Your job is to intelligently infer missing transaction details using structured catalog data.

Vendor: {vendor_name}

Missing Fields: {missing_fields_str}

Item Catalog:
{item_catalog_str}

Partial Transaction Context: '{msg_content}'

Your task:
- Analyze the catalog and context above
- Suggest 1–3 highly relevant completions ONLY for the missing fields listed
- Rules:
  • Only use items from the catalog above
  • Infer price from sellingPrice if the amount field is missing
  • Suggest practical quantities (1, 2, 3, 5, etc.) if quantity is missing
  • Do not invent items not present in the catalog

Output Format:
- A JSON list of casual, conversational confirmation strings
- Each string should sound like a friendly cashier asking "did you mean...?"
- Fill in ALL missing fields naturally within the sentence
- Use "rs" for currency, keep it short and informal
- No explanations, no markdown, no extra formatting
- Example: ["did you mean you sold milk 2 quantities for 45 rs?", "did you mean you sold 1 pack of bread for 30 rs?"]
give ans in whatever lang user wants i.e{lang}
Focus on accuracy, realism, and contextual relevance."""

    # 6. Construct message payload — system + human turn
    messages_to_pass = [
        ("system", system_prompt),
        ("human", f"Based on the context and catalog, suggest completions for the missing fields: {missing_fields_str}"),
    ]

    # 7. Invoke LLM
    response = llm.invoke(messages_to_pass)

    # 8. Ensure response content is a plain string before wrapping
    raw_content = response.content if hasattr(response, "content") else str(response)

    # 9. Validate that the LLM returned parseable JSON; log a warning if not
    try:
        parsed_response = json.loads(raw_content)
        if not isinstance(parsed_response, list):
            print("Warning: LLM response is valid JSON but not a list:", parsed_response)
    except json.JSONDecodeError:
        print("Warning: LLM response is not valid JSON. Raw output:", raw_content)

    # 10. Wrap in AIMessage for consistent graph state handling
    return {"messages": [AIMessage(content=raw_content)]}
```

# agents\text_db_agent.py

```py
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
        config = {
        "configurable": {
            "thread_id": str(num)
        },
        "metadata": {
            "vendor_id": vendor_id,
            "conversation_id": num,
            "application": "transaction-agent"
        },
        "tags": [
            "production",
            "transaction-classifier"
        ]
    }
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
```

# agents\waste_agent.py

```py
# agents/waste_agent.py

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from llm import llm
from datetime import datetime, timedelta
from bson import ObjectId
from db import get_db

# ─────────────────────────────────────────
# STATE DEFINITION
# ─────────────────────────────────────────

class WasteState(TypedDict):
    vendor_id: str
    raw_data: list
    analysis: str
    waste_insights: List[str]

# ─────────────────────────────────────────
# DB FETCH
# ─────────────────────────────────────────

async def fetch_vendor_waste_records(vendor_id: str, days: int = 7) -> list:
    db = get_db()
    
    since_date = datetime.utcnow() - timedelta(days=days)
    
    query = {
        "vendorId": ObjectId(vendor_id),
        "date": {"$gte": since_date}
    }
    
    print(f"🗑️ Fetching waste records for vendor {vendor_id} (last {days} days)...")
    
    cursor = db["dailyrecords"].find(query).sort("date", -1)
    records = await cursor.to_list(length=days)
    
    print(f"✅ Found {len(records)} waste records")
    
    return records

# ─────────────────────────────────────────
# NODES
# ─────────────────────────────────────────

async def fetch_data_node(state: WasteState) -> WasteState:
    print(f"[fetch_data] Loading waste data for vendor {state['vendor_id']} ...")
    raw = await fetch_vendor_waste_records(state["vendor_id"], days=7) 
    return {**state, "raw_data": raw}

def agent_node(state: WasteState) -> WasteState:
    print("[agent] Analysing waste data and generating insights ...")
    
    waste_summaries = []
    
    for day in state["raw_data"]:
        # Extract only wasted items
        wasted_list = day.get("wastedItems", [])
        if wasted_list:
            wasted_str = ", ".join(f"{i['item']}×{i['quantity']}" for i in wasted_list)
            waste_summaries.append(f"Date: {day['date']} -> Wasted: {wasted_str}")
            # ❌ Removed math calculation here to prevent crashes from empty strings/decimals

    if not waste_summaries:
        return {
            **state, 
            "analysis": "No waste recorded.", 
            "waste_insights": ["Great job! You had zero wasted items in the last 7 days."]
        }

    history_text = "\n".join(waste_summaries)

    prompt = f"""
You are a smart financial advisor helping a street food vendor minimize food waste.

Below is the vendor's waste history for the past 7 days:
{history_text}

Task:
1. Identify which items are being wasted the most.
2. Estimate the business impact (mention that consistent waste eats directly into their profit margins).
3. Provide exactly 3 actionable, short bullet points to help them fix this. 
   CRITICAL: For each wasted item, explicitly suggest a percentage (%) to reduce production by, or an exact quantity to cut down.
   Format each line as: "<Item/Topic>: <Short advice with % or quantity reduction>"
   Example: "Samosas: Reduce preparation by 20% (or make 15 fewer) in the afternoon to avoid throwing them away."
   Example: "Loss Warning: Throwing away 10 items daily equals losing roughly ₹150-₹200 in profit."

Keep the language simple, encouraging, and easy for a street vendor to understand.
Return ONLY the bullet point lines, nothing else. No intro, no outro.
""".strip()

    response = llm.invoke(prompt)
    insights_text = response.content.strip()
    insights = [line.strip().lstrip('•*- ') for line in insights_text.splitlines() if line.strip()]

    return {**state, "analysis": insights_text, "waste_insights": insights}

def output_node(state: WasteState) -> WasteState:
    print("\n" + "═" * 55)
    print("   🗑️  WASTE & LOSS INSIGHTS")
    print("═" * 55)
    for line in state["waste_insights"]:
        print(f"  • {line}")
    print("═" * 55 + "\n")
    return state

# ─────────────────────────────────────────
# GRAPH BUILDER
# ─────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(WasteState)
    
    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("agent",      agent_node)
    graph.add_node("output",     output_node)
    
    graph.set_entry_point("fetch_data")
    graph.add_edge("fetch_data", "agent")
    graph.add_edge("agent",      "output")
    graph.add_edge("output",     END)
    
    return graph.compile()

# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────

if __name__ == "__main__":
    app = build_graph()

    initial_state: WasteState = {
        "vendor_id": "69c7ee1bb5546e91df1818eb",
        "raw_data": [],
        "analysis": "",
        "waste_insights": [],
    }

    # If running locally to test
    final_state = asyncio.run(app.ainvoke(initial_state))
```

# api.py

```py
import json
import asyncio
import os
import uuid
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tools.save_transaction import save_transaction
from tools.sp_text import speech_to_text_base, speech_to_text_turbo
from tools.delete_recommendation import delete_recommendation
from agents.text_db_agent import main
from agents.waste_agent import build_graph as build_waste_graph


app = FastAPI(title="FinWell Agent API", version="1.0.0")

origins = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AgentQuery(BaseModel):
    userId: str
    query: str
    lang: str = "english"


@app.post("/api/speech_msg")
async def speech_input(
    meta: str = Form(...),
    audio: UploadFile = File(...),
    lang: str = Form(...)
):
    try:
        parsed = json.loads(meta)
        user_id = parsed["userId"]
        timestamp = str(parsed["timestamp"])
        print(f"Processing audio for User: {user_id}")

        audio_bytes = await audio.read()
        unique_file_id = str(uuid.uuid4())
        temp_path = f"temp_input_audio_{unique_file_id}.m4a"

        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        async def generate_response():
            try:
                yield f"data: {json.dumps({'status': 'Analyzing audio...'})}\n\n"

                task_base = asyncio.to_thread(speech_to_text_base, temp_path, lang)
                fast_text = await task_base
                yield f"data: {json.dumps({'status': 'fast_text', 'text': fast_text})}\n\n"

                yield f"data: {json.dumps({'status': 'Refining text for accuracy...'})}\n\n"

                task_turbo = asyncio.to_thread(speech_to_text_turbo, temp_path, lang)
                accurate_text = await task_turbo
                yield f"data: {json.dumps({'status': 'accurate_text_ready', 'text': accurate_text})}\n\n"

                if not accurate_text or len(accurate_text.strip()) == 0:
                    accurate_text = fast_text

                yield f"data: {json.dumps({'status': 'AI Agent processing...'})}\n\n"

                async for step_update in main(voice_text=str(accurate_text), vendor_id=user_id, num=-1):
                    yield f"data: {json.dumps(step_update)}\n\n"

                    if step_update.get("stage") == "complete":
                        inserted_id = await save_transaction(step_update, user_id, None)
                        yield f"data: {json.dumps({'stage': 'saved', 'id': inserted_id})}\n\n"

            except Exception as stream_err:
                print(f"!!! STREAM ERROR: {stream_err}")
                yield f"data: {json.dumps({'error': str(stream_err)})}\n\n"
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        return StreamingResponse(generate_response(), media_type="text/event-stream")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing speech input: {str(e)}")


@app.post("/api/recommend_msg")
async def recommend_msg(
    meta: str = Form(...),
    lang: str = Form(...)
):
    try:
        parsed = json.loads(meta)
        num = parsed.get("num")
        vendor_id = parsed.get("userId")
        msg = parsed.get("msg")
        print(msg)
        if not vendor_id or not msg:
            raise HTTPException(status_code=400, detail="Missing userId or msg")

        print(f"Processing message for User: {vendor_id}")

        async def generate_response():
            try:
                yield f"data: {json.dumps({'status': 'Processing message...'})}\n\n"

                try:
                    deleted_count = await delete_recommendation(vendor_id)
                    yield f"data: {json.dumps({'stage': 'cleanup', 'deleted': deleted_count})}\n\n"
                except Exception as del_err:
                    yield f"data: {json.dumps({'stage': 'cleanup_error', 'error': str(del_err)})}\n\n"

                async for step_update in main(voice_text=msg, vendor_id=vendor_id, num=num):
                    yield f"data: {json.dumps(step_update)}\n\n"

                    if step_update.get("stage") == "complete":
                        try:
                            inserted_id = await save_transaction(
                                agent_output=step_update,
                                vendor_id=vendor_id,
                                voice_url=None
                            )
                            yield f"data: {json.dumps({'stage': 'saved', 'id': inserted_id})}\n\n"
                        except Exception as db_err:
                            yield f"data: {json.dumps({'stage': 'db_error', 'error': str(db_err)})}\n\n"

            except Exception as stream_err:
                yield f"data: {json.dumps({'error': str(stream_err)})}\n\n"

        return StreamingResponse(generate_response(), media_type="text/event-stream")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@app.post("/api/next_day_suggestions")
async def next_day_suggestions(
    meta: str = Form(...)
):
    try:
        parsed = json.loads(meta)
        vendor_id = parsed.get("userId")

        if not vendor_id:
            raise HTTPException(status_code=400, detail="Missing userId")

        print(f"📦 Generating next-day suggestions for vendor: {vendor_id}")

        from agents.next_day_agent import build_graph

        app_graph = build_graph()

        initial_state = {
            "vendor_id":   vendor_id,
            "raw_data":    [],
            "analysis":    "",
            "suggestions": [],
            "lang":        "",   # ← fix: was missing
        }

        final_state = await app_graph.ainvoke(initial_state)

        return {"suggestions": final_state["suggestions"]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating suggestions: {str(e)}")


@app.post("/api/waste_insights")
async def waste_insights(meta: str = Form(...)):
    try:
        parsed = json.loads(meta)
        vendor_id = parsed.get("userId")

        if not vendor_id or vendor_id in ["undefined", "null"]:
            raise HTTPException(status_code=400, detail="Missing or invalid userId")

        print(f"🗑️ Generating waste insights for vendor: {vendor_id}")

        waste_graph = build_waste_graph()

        initial_state = {
            "vendor_id":     vendor_id,
            "raw_data":      [],
            "analysis":      "",
            "waste_insights": [],
        }

        final_state = await waste_graph.ainvoke(initial_state)

        return {"insights": final_state["waste_insights"]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating waste insights: {str(e)}")
```

# db.py

```py
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = client[os.getenv("DB_NAME")]

def get_db():
    return db
```

# llm.py

```py
import os
from dotenv import load_dotenv
load_dotenv()

# from langchain_groq import ChatGroq

# from langchain_openai import ChatOpenAI

# llm = ChatGroq(
#     model="llama-3.1-8b-instant",  # fast + cheap
#     temperature=0
# )
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4.1-mini",   # BEST choice for your use case
    temperature=0
)

print("LLM INITIALIZATION")
print('LLM INITIALIZATION')
```

# requirements.txt

```txt
��annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.13.0
certifi==2026.2.25
charset-normalizer==3.4.6
click==8.3.1
colorama==0.4.6
distro==1.9.0
dotenv==0.9.9
fastapi==0.135.2
filelock==3.25.2
fsspec==2026.2.0
groq==0.37.1
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.11
imageio-ffmpeg==0.6.0
Jinja2==3.1.6
jiter==0.13.0
jsonpatch==1.33
jsonpointer==3.1.1
langchain-core==1.2.22
langchain-groq==1.1.2
langchain-openai==1.1.12
langgraph==1.1.3
langgraph-checkpoint==4.0.1
langgraph-prebuilt==1.0.8
langgraph-sdk==0.3.12
langsmith==0.7.22
llvmlite==0.46.0
MarkupSafe==3.0.3
more-itertools==10.8.0
mpmath==1.3.0
networkx==3.6.1
numba==0.64.0
numpy==2.4.3
openai==2.30.0
openai-whisper==20250625
orjson==3.11.7
ormsgpack==1.12.2
packaging==26.0
pydantic==2.12.5
pydantic_core==2.41.5
python-dotenv==1.2.2
python-multipart==0.0.22
PyYAML==6.0.3
regex==2026.2.28
requests==2.33.0
requests-toolbelt==1.0.0
setuptools==81.0.0
sniffio==1.3.1
starlette==1.0.0
sympy==1.14.0
tenacity==9.1.4
tiktoken==0.12.0
torch==2.11.0
tqdm==4.67.3
typing==3.7.4.3
typing-inspection==0.4.2
typing_extensions==4.15.0
urllib3==2.6.3
uuid_utils==0.14.1
uvicorn==0.42.0
xxhash==3.6.0
zstandard==0.25.0

```

# schemas\__init__.py

```py

```

# schemas\check.py

```py
# schemas/check.py
from pydantic import BaseModel, Field
from typing import List

class Check(BaseModel):
    flag: bool = Field(
        ..., 
        description="True if the user provided enough info for a complete transaction, False if info is missing."
    )
    missing: List[str] = Field(
        default_factory=list, 
        description="A list of the missing required field names (e.g., ['amount', 'item']). Leave empty if flag is True."
    )
```

# schemas\recommend.py

```py
from typing import Annotated , Literal , Optional
from pydantic import BaseModel

from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date

class Recommend(BaseModel):
    suggest : List[str]
     
```

# schemas\state.py

```py
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]
    recent_msg:str
    vendor_id: str
    vendor_attributes: dict
```

# schemas\transaction_type.py

```py
from typing import Annotated , Literal , Optional
from pydantic import BaseModel

from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date

class TransactionType(BaseModel):
    transaction_type: Literal[
        "sale", "expense", "udhar"
    ] = Field(..., alias="type")
```

# schemas\transactions.py

```py
from typing import Annotated , Literal , Optional
from pydantic import BaseModel

from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date

class SaleTransaction(BaseModel):
    transcript: str
    
    transaction_type: Literal[
        "sale", "expense", "udhar_given", "udhar_received", "waste", "unsold", "correction"
    ] = Field(..., alias="type")
    
   
    item: str
    quantity: float
    pricePerUnit: float

    amount: float

    flags: List[Literal["approximation_used", "missing_quantity", "ambiguous_item"]] = Field(
        default_factory=list
    )
    confidence: float = Field(..., ge=0.0, le=1.0) 
    

class ExpenseTransaction(BaseModel):
    transcript: str
    
    transaction_type: Literal[
        "sale", "expense", "udhar_given", "udhar_received", "waste", "unsold", "correction"
    ] = Field(..., alias="type")
    
    amount: float
    
    expenseType: str = Field(description="The category of the expense, e.g., transport, rent, supplies")
    note: Optional[str] = None
    
    flags: List[Literal["approximation_used", "ambiguous_expense"]] = Field(
        default_factory=list
    )
    
    confidence: float = Field(..., ge=0.0, le=1.0)


class UdharTransaction(BaseModel):
    transcript: str
    
    transaction_type: Literal["udhar_given", "udhar_received"] = Field(
        ..., 
        alias="type",
        description="Use 'udhar_given' if the user lent money/goods, and 'udhar_received' if the user borrowed money/goods."
    )
    
    amount: float
    
    personName: str = Field(..., description="The name of the person involved in the udhar transaction.")
    
    flags: List[Literal["ambiguous_person", "approximation_used"]] = Field(
        default_factory=list
    )
    
    confidence: float = Field(..., ge=0.0, le=1.0)



```

# schemas\vendor.py

```py
from typing import TypedDict, List

class VendorState(TypedDict):
    vendor_id:   str
    raw_data:    list
    analysis:    str
    suggestions: List[str]
    lang:        str        # ← add this
```

# tools\__init__.py

```py

```

# tools\delete_recommendation.py

```py
from datetime import datetime
from bson import ObjectId
from db import get_db

async def delete_recommendation(vendor_id: str):
    db = get_db()

    query = {
        "vendorId": ObjectId(vendor_id)
    }

    print("🗑️ Delete Query:", query)

    result = await db["recommendations"].delete_many(query)

    print(f"✅ Deleted {result.deleted_count} documents")

    return result.deleted_count
```

# tools\lang.py

```py
from bson import ObjectId
from db import get_db

async def get_vendor_language(vendor_id: str) -> str:
    db = get_db()

    query = {
        "_id": ObjectId(vendor_id)
    }

    print(f"🌐 Fetching language for vendor {vendor_id}...")

    vendor = await db["vendors"].find_one(query)

    if not vendor:
        print("❌ Vendor not found")
        return "en"  # default fallback

    language = vendor.get("language", "en")

    print(f"✅ Language found: {language}")

    return language
```

# tools\save_recommendation.py

```py
from datetime import datetime
from bson import ObjectId
from db import get_db

async def save_recommendation(vendor_id: str,msgs ,num):
    db = get_db()
    now = datetime.utcnow()
    
    document = {
        "vendorId":     ObjectId(vendor_id),
        "threadId":    num,
        "date":         now,
        "msgs": msgs
    }

    print("📄 Document to insert:", document)
    result = await db["recommendations"].insert_one(document)
    print("✅ Inserted ID:", result.inserted_id)
    return str(result.inserted_id)


```

# tools\save_transaction.py

```py
from datetime import datetime
from bson import ObjectId
from db import get_db
import httpx

async def save_sale_event(data: dict, vendor_id: str, voice_url: str = None):
    db = get_db()
    now = datetime.utcnow()

    document = {
        "vendorId":     vendor_id,
        "timestamp":    now,
        "date":         now,
        "voiceUrl":     voice_url,
        "transcript":   data.get("transcript"),
        "item":         data.get("item"),
        "quantity":     data.get("quantity"),
        "pricePerUnit": data.get("pricePerUnit"),
        "amount":       data.get("amount"),
    }

    print("📄 Document to insert:", document)
    result = await db["saleevents"].insert_one(document)
    print("✅ Inserted ID:", result.inserted_id)
    return str(result.inserted_id)

NODE_API_URL = "http://localhost:5000/api/internal/update-daily"

async def save_transaction(agent_output: dict, vendor_id: str, voice_url: str = None):
    print("🔁 save_transaction called with stage:", agent_output.get("stage"))
    print("📦 agent_output:", agent_output)

    if agent_output.get("stage") != "complete":
        raise ValueError(f"Agent stage is '{agent_output.get('stage')}', not 'complete'")

    data = agent_output["data"]
    tx_type = data.get("transaction_type")
    print("💳 transaction_type:", tx_type)

    if tx_type == "sale":
        inserted_id = await save_sale_event(data, vendor_id, voice_url)
        # 🔥 CALL NODE API HERE
        async with httpx.AsyncClient() as client:
            await client.post(
                NODE_API_URL,
                json={
                    "vendorId": vendor_id,
                    "date": datetime.utcnow().isoformat()
                }
            )

        return inserted_id
    else:
        raise ValueError(f"Unknown transaction_type: '{tx_type}'")
```

# tools\sp_text.py

```py
import os
import subprocess
import numpy as np
import imageio_ffmpeg
import warnings
import sys

from agents.text_db_agent import main

sys.stdout.reconfigure(encoding="utf-8")

# (Optional) Remove FP16 warnings
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")


# -------------------------------
# 1️⃣  Setup FFmpeg from imageio
# -------------------------------
ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

# Force Whisper model downloads to D:
os.environ["WHISPER_CACHE_DIR"] = "D:/WhisperCache"
os.makedirs(os.environ["WHISPER_CACHE_DIR"], exist_ok=True)


# -------------------------------
# 2️⃣  Patch Whisper audio loader
# -------------------------------
def load_audio(file: str, sr: int = 16000):
    """
    Load audio using FFmpeg from imageio_ffmpeg
    """
    cmd = [
        ffmpeg_path,
        "-nostdin",
        "-i", file,
        "-ac", "1",
        "-ar", str(sr),
        "-f", "s16le",
        "-"
    ]

    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    audio = np.frombuffer(out, np.int16).astype(np.float32) / 32768.0
    return audio.flatten()


# Override Whisper audio function BEFORE importing whisper
import whisper.audio
whisper.audio.load_audio = load_audio


# -------------------------------
# 3️⃣  Load Whisper + Transcribe
# -------------------------------
import whisper
print("Loading Whisper Base model...")
model_base = whisper.load_model("base")

print("Loading Whisper Turbo model...")
model_turbo = whisper.load_model("large-v3-turbo")

def speech_to_text_base(audio_path: str, lang: str):
    """
    Converts audio to text using the fast Base model.
    """
    result = model_base.transcribe(
        audio_path,
        language=lang,
        task="translate"   # ensures English output always
    )
    
    text = result.get("text", "").strip()
    print(f"[Whisper Base] Extracted Text: {text}")
    return text


def speech_to_text_turbo(audio_path: str, lang: str):
    """
    Converts audio to text using the highly accurate Turbo model.
    """
    result = model_turbo.transcribe(
        audio_path,
        language=lang,
        task="translate"   # ensures English output always
    )
    
    text = result.get("text", "").strip()
    print(f"[Whisper Turbo] Extracted Text: {text}")
    return text
```

# tools\vendor_attributes.py

```py
# tools/get_vendor_attributes.py

from db import db
from bson import ObjectId


async def get_vendor_attributes(vendor_id: str) -> dict:  # ← just a string, no State
    vendor = await db.vendors.find_one(
        {"_id": ObjectId(vendor_id)},
        {"_id": 0, "name": 1, "language": 1, "items": 1}
    )

    if not vendor:
        return {"error": "Vendor not found"}

    insights = await db.insights.find_one(
        {"vendorId": ObjectId(vendor_id)},
        {
            "_id": 0,
            "bestItems": 1,
            "avgDailyIncome": 1,
            "avgDailyExpense": 1,
            "avgProfit": 1,
            "wastePercentage": 1,
        }
    )

    # Build item catalog with margin info
    item_catalog = []
    for i in vendor.get("items", []):
        margin = i["sellingPrice"] - i["costPrice"]
        margin_pct = round((margin / i["costPrice"]) * 100, 1)
        item_catalog.append({
            "item": i["item"],
            "costPrice": i["costPrice"],
            "sellingPrice": i["sellingPrice"],
            "unit": i["unit"],
            "margin": margin,
            "marginPercent": margin_pct
        })

    # Enrich bestItems with catalog data
    best_items = []
    if insights:
        catalog_map = {i["item"]: i for i in item_catalog}
        for b in insights.get("bestItems", []):
            entry = {**b}
            if b["item"] in catalog_map:
                entry["sellingPrice"] = catalog_map[b["item"]]["sellingPrice"]
                entry["margin"] = catalog_map[b["item"]]["margin"]
            best_items.append(entry)

    return {
        "vendorName": vendor.get("name"),
        "language": vendor.get("language"),
        "itemCatalog": item_catalog,
        "bestItems": best_items,
        "financials": {
            "avgDailyIncome": insights.get("avgDailyIncome") if insights else None,
            "avgDailyExpense": insights.get("avgDailyExpense") if insights else None,
            "avgProfit": insights.get("avgProfit") if insights else None,
            "wastePercentage": insights.get("wastePercentage") if insights else None,
        }
    }
```

