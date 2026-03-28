import json
from typing import Annotated , Literal , Optional
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph , START , END
from langgraph.graph.message import add_messages
from schemas.transaction_type import TransactionType
from schemas.state import State
from llm import llm
from langchain_core.messages import AIMessage

# Inside query_checker.py

def query_checker(state: State):
    msg_content = state['messages'][-1].content
    
    prompt = f'''You are a classification agent. Your ONLY job is to check if the user's message type is a sale / expense / udhar
    Then basically store it like wise in transaction_type
    
    User Message: "{msg_content}"
    '''

    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]

    # ... rest of your code ...
    check_llm = llm.with_structured_output(TransactionType)
    parsed_check = check_llm.invoke(messages_to_pass)
    
    return {"messages": [AIMessage(content=parsed_check.model_dump_json())]}