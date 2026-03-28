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

# Inside query_checker.py

def query_checker_sale(state: State):
    msg_content = state['messages'][0].content
    
    prompt = f'''You are a validation agent. Your ONLY job is to verify if the user's message contains enough information to log a transaction.
    Do NOT extract the actual values into the schema. Only evaluate completeness.
    
    Required information to check for:
    1. Type: Can you infer if it's a sale, expense, or udhar?
    2. Amount: Is the total monetary value stated?
    3. Item: What was sold/bought?
    4. Quantity: How many were sold/bought? (ONLY required for physical goods like sales).
    
    EXAMPLES OF COMPLETE MESSAGES (Output flag = true, missing = []):
    - "I sold 2 pizzas for 80 rupees" (Has type, amount, item, and quantity)
    - "I spent 150 on an uber" (Has type, amount, item. Quantity not needed for transport)
    - "I gave 500 udhar to Rahul" (Has type, amount, person. Quantity/Item not needed)

    EXAMPLES OF INCOMPLETE MESSAGES (Output flag = false, list missing fields):
    - "I sold pizzas for 80 rupees" -> missing = ["quantity"]
    - "I sold 2 pizzas" -> missing = ["amount"]
    - "I spent 500 today" -> missing = ["item"]
    
    User Message: "{msg_content}"
    '''

    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]

    # ... rest of your code ...
    check_llm = llm.with_structured_output(Check)
    parsed_check = check_llm.invoke(messages_to_pass)
    
    return {"messages": [AIMessage(content=parsed_check.model_dump_json())]}

def query_checker_expense(state: State):
    msg_content = state['messages'][0].content
    
    prompt = f'''You are a validation agent specialized in EXPENSES. Your ONLY job is to verify if the user's message contains enough information to log an expense transaction.
    Do NOT extract the actual values into the schema. Only evaluate completeness.
    
    Required information to check for:
    1. Type: Is this clearly an expense (spending money on services, supplies, or bills)?
    2. Amount: Is the total monetary value stated?
    3. ExpenseType: What was the money spent on? (e.g., transport, rent, supplies, food).
    
    EXAMPLES OF COMPLETE MESSAGES (Output flag = true, missing = []):
    - "I spent 150 on an auto rickshaw" (Has type, amount, and expenseType)
    - "Paid 5000 for the shop rent" (Has type, amount, and expenseType)
    - "Bought 200 rupees worth of cleaning supplies" (Has type, amount, and expenseType)

    EXAMPLES OF INCOMPLETE MESSAGES (Output flag = false, list missing fields):
    - "I spent 500 today" -> missing = ["expenseType"]
    - "I paid the electricity bill" -> missing = ["amount"]
    
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
    msg_content = state['messages'][0].content
    
    prompt = f'''You are a validation agent specialized in UDHAR (Credit/Debt). Your ONLY job is to verify if the user's message contains enough information to log an udhar transaction.
    Do NOT extract the actual values into the schema. Only evaluate completeness.
    
    Required information to check for:
    1. Type: Is it clear whether the user is GIVING udhar (lending) or RECEIVING udhar (borrowing/being paid back)?
    2. Amount: Is the total monetary value stated?
    3. PersonName: Is the specific name of the person involved mentioned?
    
    EXAMPLES OF COMPLETE MESSAGES (Output flag = true, missing = []):
    - "I gave 500 udhar to Rahul" (Has type, amount, and personName)
    - "Suresh took 1000 rupees from me on credit" (Has type, amount, and personName)
    - "Amit paid back the 200 rupees he owed me" (Has type, amount, and personName)

    EXAMPLES OF INCOMPLETE MESSAGES (Output flag = false, list missing fields):
    - "I gave 500 udhar today" -> missing = ["personName"]
    - "Rahul took some money on credit" -> missing = ["amount"]
    - "I gave udhar to Amit" -> missing = ["amount"]
    
    User Message: "{msg_content}"
    '''

    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]

    check_llm = llm.with_structured_output(Check)
    parsed_check = check_llm.invoke(messages_to_pass)
    
    return {"messages": [AIMessage(content=parsed_check.model_dump_json())]}