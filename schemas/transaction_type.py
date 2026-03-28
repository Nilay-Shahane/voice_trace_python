from typing import Annotated , Literal , Optional
from pydantic import BaseModel

from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date

class TransactionType(BaseModel):
    transaction_type: Literal[
        "sale", "expense", "udhar"
    ] = Field(..., alias="type")