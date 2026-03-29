# agents/next_day_agent.py

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from schemas.vendor import VendorState
from llm import llm
from datetime import datetime, timedelta
from bson import ObjectId
from db import get_db


# ─────────────────────────────────────────
# DB FETCH
# ─────────────────────────────────────────

async def fetch_vendor_daily_records(vendor_id: str, days: int = 7) -> list:
    db = get_db()

    since_date = datetime.utcnow() - timedelta(days=days)

    query = {
        "vendorId": ObjectId(vendor_id),
        "date": {"$gte": since_date}
    }

    print(f"📦 Fetching daily records for vendor {vendor_id} (last {days} days)...")

    cursor = db["dailyrecords"].find(query).sort("date", -1)
    records = await cursor.to_list(length=days)

    print(f"✅ Found {len(records)} records")

    return records


# ─────────────────────────────────────────
# NODES
# ─────────────────────────────────────────

async def fetch_data_node(state: VendorState) -> VendorState:
    print(f"[fetch_data] Loading data for vendor {state['vendor_id']} ...")
    # Native await! No more asyncio.run()
    raw = await fetch_vendor_daily_records(state["vendor_id"], days=7) 
    return {**state, "raw_data": raw}


def agent_node(state: VendorState) -> VendorState:
    print("[agent] Analysing data and generating suggestions ...")

    day_summaries = []
    for day in state["raw_data"]:
        sold   = ", ".join(f"{i['item']}×{i['quantity']}" for i in day.get("itemsSold",  []))
        unsold = ", ".join(f"{i['item']}×{i['quantity']}" for i in day.get("unsoldItems", []))
        wasted = ", ".join(f"{i['item']}×{i['quantity']}" for i in day.get("wastedItems", []))
        day_summaries.append(
            f"Date: {day['date']}\n"
            f"  Sold    : {sold   or 'none'}\n"
            f"  Unsold  : {unsold or 'none'}\n"
            f"  Wasted  : {wasted or 'none'}"
        )

    history_text = "\n\n".join(day_summaries)

    prompt = f"""
You are a smart business assistant helping a small food vendor plan stock for tomorrow.

Below is the vendor's sales history for the past few days (sold / unsold / wasted items):

{history_text}

Task:
1. Look at sell-through trends (what sells fast vs. what stays unsold or gets wasted).
2. Generate a "Next-Day Stock Suggestion" — one line per item.
   Format: "<item>: prepare <quantity> units — <short reason>"
   - Increase quantity for fast-selling items.
   - Decrease or skip items that are repeatedly unsold or wasted.
   - Keep language simple so a street-vendor can understand.

Return ONLY the suggestion lines, nothing else.
""".strip()

    response = llm.invoke(prompt)
    suggestions_text = response.content.strip()
    suggestions = [line.strip() for line in suggestions_text.splitlines() if line.strip()]

    return {**state, "analysis": suggestions_text, "suggestions": suggestions}


def output_node(state: VendorState) -> VendorState:
    print("\n" + "═" * 55)
    print("   📦  NEXT-DAY STOCK SUGGESTIONS")
    print("═" * 55)
    for line in state["suggestions"]:
        print(f"  • {line}")
    print("═" * 55 + "\n")
    return state


# ─────────────────────────────────────────
# GRAPH
# ─────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(VendorState)

    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("agent",      agent_node)
    graph.add_node("output",     output_node)

    graph.set_entry_point("fetch_data")
    graph.add_edge("fetch_data", "agent")
    graph.add_edge("agent",      "output")
    graph.add_edge("output",     END)

    return graph.compile()


# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────

if __name__ == "__main__":
    app = build_graph()

    initial_state: VendorState = {
        "vendor_id":   "69c7ee1bb5546e91df1818eb",
        "raw_data":    [],
        "analysis":    "",
        "suggestions": [],
    }

    final_state = app.invoke(initial_state)