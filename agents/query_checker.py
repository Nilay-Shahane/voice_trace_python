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