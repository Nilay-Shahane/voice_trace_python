from datetime import datetime
from bson import ObjectId
from db import get_db

async def delete_recommendation(vendor_id: str):
    db = get_db()

    query = {
        "vendorId": ObjectId(vendor_id)
    }

    print("🗑️ Delete Query:", query)

    result = await db["recommendations"].delete_many(query)

    print(f"✅ Deleted {result.deleted_count} documents")

    return result.deleted_count