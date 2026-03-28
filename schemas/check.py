# schemas/check.py
from pydantic import BaseModel, Field
from typing import List

class Check(BaseModel):
    flag: bool = Field(
        ..., 
        description="True if the user provided enough info for a complete transaction, False if info is missing."
    )
    missing: List[str] = Field(
        default_factory=list, 
        description="A list of the missing required field names (e.g., ['amount', 'item']). Leave empty if flag is True."
    )