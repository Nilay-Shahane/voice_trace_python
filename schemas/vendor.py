from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
class VendorState(TypedDict):
    vendor_id: str
    raw_data: List[Dict[str, Any]]   # last N days of daily-summary docs
    analysis: str                    # intermediate analysis text
    suggestions: List[str]