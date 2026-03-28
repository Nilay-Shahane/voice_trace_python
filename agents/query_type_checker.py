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