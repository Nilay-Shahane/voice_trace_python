from typing import TypedDict, List

class VendorState(TypedDict):
    vendor_id:   str
    raw_data:    list
    analysis:    str
    suggestions: List[str]
    lang:        str        # ← add this