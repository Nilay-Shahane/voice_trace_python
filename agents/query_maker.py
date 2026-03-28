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