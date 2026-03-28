from datetime import datetime
from bson import ObjectId
from db import get_db

async def save_recommendation(vendor_id: str,msgs ,num):
    db = get_db()
    now = datetime.utcnow()
    
    document = {
        "vendorId":     ObjectId(vendor_id),
        "threadId":    num,
        "date":         now,
        "msgs": msgs
    }

    print("📄 Document to insert:", document)
    result = await db["recommendations"].insert_one(document)
    print("✅ Inserted ID:", result.inserted_id)
    return str(result.inserted_id)

