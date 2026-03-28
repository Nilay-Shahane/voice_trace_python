# tools/get_vendor_attributes.py

from db import db
from bson import ObjectId


async def get_vendor_attributes(vendor_id: str) -> dict:  # ← just a string, no State
    vendor = await db.vendors.find_one(
        {"_id": ObjectId(vendor_id)},
        {"_id": 0, "name": 1, "language": 1, "items": 1}
    )

    if not vendor:
        return {"error": "Vendor not found"}

    insights = await db.insights.find_one(
        {"vendorId": ObjectId(vendor_id)},
        {
            "_id": 0,
            "bestItems": 1,
            "avgDailyIncome": 1,
            "avgDailyExpense": 1,
            "avgProfit": 1,
            "wastePercentage": 1,
        }
    )

    # Build item catalog with margin info
    item_catalog = []
    for i in vendor.get("items", []):
        margin = i["sellingPrice"] - i["costPrice"]
        margin_pct = round((margin / i["costPrice"]) * 100, 1)
        item_catalog.append({
            "item": i["item"],
            "costPrice": i["costPrice"],
            "sellingPrice": i["sellingPrice"],
            "unit": i["unit"],
            "margin": margin,
            "marginPercent": margin_pct
        })

    # Enrich bestItems with catalog data
    best_items = []
    if insights:
        catalog_map = {i["item"]: i for i in item_catalog}
        for b in insights.get("bestItems", []):
            entry = {**b}
            if b["item"] in catalog_map:
                entry["sellingPrice"] = catalog_map[b["item"]]["sellingPrice"]
                entry["margin"] = catalog_map[b["item"]]["margin"]
            best_items.append(entry)

    return {
        "vendorName": vendor.get("name"),
        "language": vendor.get("language"),
        "itemCatalog": item_catalog,
        "bestItems": best_items,
        "financials": {
            "avgDailyIncome": insights.get("avgDailyIncome") if insights else None,
            "avgDailyExpense": insights.get("avgDailyExpense") if insights else None,
            "avgProfit": insights.get("avgProfit") if insights else None,
            "wastePercentage": insights.get("wastePercentage") if insights else None,
        }
    }