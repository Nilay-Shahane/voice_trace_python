from bson import ObjectId
from db import get_db

async def get_vendor_language(vendor_id: str) -> str:
    db = get_db()

    query = {
        "_id": ObjectId(vendor_id)
    }

    print(f"🌐 Fetching language for vendor {vendor_id}...")

    vendor = await db["vendors"].find_one(query)

    if not vendor:
        print("❌ Vendor not found")
        return "en"  # default fallback

    language = vendor.get("language", "en")

    print(f"✅ Language found: {language}")

    return language