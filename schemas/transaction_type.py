from typing import Literal 
from pydantic import BaseModel, Field


class TransactionType(BaseModel):
    transaction_type: Literal[
        "sale", "expense", "udhar"
    ] = Field(..., alias="type")