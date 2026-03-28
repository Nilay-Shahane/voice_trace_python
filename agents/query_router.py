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