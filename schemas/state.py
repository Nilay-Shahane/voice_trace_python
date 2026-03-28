
from typing import Annotated , Literal , Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class State(TypedDict):
    messages:Annotated[list,add_messages]