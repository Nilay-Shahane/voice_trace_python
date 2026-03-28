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

def query_type_checker(state: State):
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
def route_by_type(state: State) -> str:
    """
    Reads the output from the intent router (query_type_checker) 
    and returns the string corresponding to the next node path.
    """
    # Get the content of the most recent message
    last_message = state['messages'][-1].content
    
    try:
        # Parse the JSON output from the LLM
        type_data = json.loads(last_message)
        
        # Extract the 'type' field. 
        # Default to 'sale' if for some reason the field is missing.
        intent = type_data.get('type', 'sale') 
        
        # Ensure the LLM didn't hallucinate a weird category
        if intent in ['sale', 'expense', 'udhar']:
            return intent
        else:
            return 'sale' # Fallback for unexpected outputs
            
    except json.JSONDecodeError:
        # If the LLM failed to output valid JSON, default to sale
        print("ERROR: Could not decode JSON in route_by_type. Falling back to 'sale'.")
        return 'sale'