from typing import Annotated , Literal , Optional
from pydantic import BaseModel

from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date

class SaleTransaction(BaseModel):
    transcript: str
    
    transaction_type: Literal[
        "sale", "expense", "udhar_given", "udhar_received", "waste", "unsold", "correction"
    ] = Field(..., alias="type")
    
   
    item: str
    quantity: float
    pricePerUnit: float

    amount: float

    flags: List[Literal["approximation_used", "missing_quantity", "ambiguous_item"]] = Field(
        default_factory=list
    )
    confidence: float = Field(..., ge=0.0, le=1.0) 
    

class ExpenseTransaction(BaseModel):
    transcript: str
    
    transaction_type: Literal[
        "sale", "expense", "udhar_given", "udhar_received", "waste", "unsold", "correction"
    ] = Field(..., alias="type")
    
    amount: float
    
    expenseType: str = Field(description="The category of the expense, e.g., transport, rent, supplies")
    note: Optional[str] = None
    
    flags: List[Literal["approximation_used", "ambiguous_expense"]] = Field(
        default_factory=list
    )
    
    confidence: float = Field(..., ge=0.0, le=1.0)


class UdharTransaction(BaseModel):
    transcript: str
    
    transaction_type: Literal["udhar_given", "udhar_received"] = Field(
        ..., 
        alias="type",
        description="Use 'udhar_given' if the user lent money/goods, and 'udhar_received' if the user borrowed money/goods."
    )
    
    amount: float
    
    personName: str = Field(..., description="The name of the person involved in the udhar transaction.")
    
    flags: List[Literal["ambiguous_person", "approximation_used"]] = Field(
        default_factory=list
    )
    
    confidence: float = Field(..., ge=0.0, le=1.0)


