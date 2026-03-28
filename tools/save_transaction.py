from datetime import datetime
from bson import ObjectId
from db import get_db
import httpx

async def save_sale_event(data: dict, vendor_id: str, voice_url: str = None):
    db = get_db()
    now = datetime.utcnow()

    document = {
        "vendorId":     vendor_id,
        "timestamp":    now,
        "date":         now,
        "voiceUrl":     voice_url,
        "transcript":   data.get("transcript"),
        "item":         data.get("item"),
        "quantity":     data.get("quantity"),
        "pricePerUnit": data.get("pricePerUnit"),
        "amount":       data.get("amount"),
    }

    print("📄 Document to insert:", document)
    result = await db["saleevents"].insert_one(document)
    print("✅ Inserted ID:", result.inserted_id)
    return str(result.inserted_id)

NODE_API_URL = "http://localhost:5000/api/internal/update-daily"

async def save_transaction(agent_output: dict, vendor_id: str, voice_url: str = None):
    print("🔁 save_transaction called with stage:", agent_output.get("stage"))
    print("📦 agent_output:", agent_output)

    if agent_output.get("stage") != "complete":
        raise ValueError(f"Agent stage is '{agent_output.get('stage')}', not 'complete'")

    data = agent_output["data"]
    tx_type = data.get("transaction_type")
    print("💳 transaction_type:", tx_type)

    if tx_type == "sale":
        inserted_id = await save_sale_event(data, vendor_id, voice_url)
        # 🔥 CALL NODE API HERE
        async with httpx.AsyncClient() as client:
            await client.post(
                NODE_API_URL,
                json={
                    "vendorId": vendor_id,
                    "date": datetime.utcnow().isoformat()
                }
            )

        return inserted_id
    else:
        raise ValueError(f"Unknown transaction_type: '{tx_type}'")