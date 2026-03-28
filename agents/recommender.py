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

def recommender(state: State):
    msg_content = state['messages'][0].content
    prompt = '''You have to greet the user with a 1 line message acknowledging their input 
    and asking for the missing financial details.'''

    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]
    print('I AM RECOMMENDERRR')
    # Recommender likely just needs to return a standard text message, not a Check schema
    response = llm.invoke(messages_to_pass)
    return {"messages": [response]}