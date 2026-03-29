# agents/waste_agent.py

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from llm import llm
from datetime import datetime, timedelta
from bson import ObjectId
from db import get_db

# ─────────────────────────────────────────
# STATE DEFINITION
# ─────────────────────────────────────────

class WasteState(TypedDict):
    vendor_id: str
    raw_data: list
    analysis: str
    waste_insights: List[str]

# ─────────────────────────────────────────
# DB FETCH
# ─────────────────────────────────────────

async def fetch_vendor_waste_records(vendor_id: str, days: int = 7) -> list:
    db = get_db()
    
    since_date = datetime.utcnow() - timedelta(days=days)
    
    query = {
        "vendorId": ObjectId(vendor_id),
        "date": {"$gte": since_date}
    }
    
    print(f"🗑️ Fetching waste records for vendor {vendor_id} (last {days} days)...")
    
    cursor = db["dailyrecords"].find(query).sort("date", -1)
    records = await cursor.to_list(length=days)
    
    print(f"✅ Found {len(records)} waste records")
    
    return records

# ─────────────────────────────────────────
# NODES
# ─────────────────────────────────────────

async def fetch_data_node(state: WasteState) -> WasteState:
    print(f"[fetch_data] Loading waste data for vendor {state['vendor_id']} ...")
    raw = await fetch_vendor_waste_records(state["vendor_id"], days=7) 
    return {**state, "raw_data": raw}

def agent_node(state: WasteState) -> WasteState:
    print("[agent] Analysing waste data and generating insights ...")
    
    waste_summaries = []
    
    for day in state["raw_data"]:
        # Extract only wasted items
        wasted_list = day.get("wastedItems", [])
        if wasted_list:
            wasted_str = ", ".join(f"{i['item']}×{i['quantity']}" for i in wasted_list)
            waste_summaries.append(f"Date: {day['date']} -> Wasted: {wasted_str}")
            # ❌ Removed math calculation here to prevent crashes from empty strings/decimals

    if not waste_summaries:
        return {
            **state, 
            "analysis": "No waste recorded.", 
            "waste_insights": ["Great job! You had zero wasted items in the last 7 days."]
        }

    history_text = "\n".join(waste_summaries)

    prompt = f"""
You are a smart financial advisor helping a street food vendor minimize food waste.

Below is the vendor's waste history for the past 7 days:
{history_text}

Task:
1. Identify which items are being wasted the most.
2. Estimate the business impact (mention that consistent waste eats directly into their profit margins).
3. Provide exactly 3 actionable, short bullet points to help them fix this. 
   CRITICAL: For each wasted item, explicitly suggest a percentage (%) to reduce production by, or an exact quantity to cut down.
   Format each line as: "<Item/Topic>: <Short advice with % or quantity reduction>"
   Example: "Samosas: Reduce preparation by 20% (or make 15 fewer) in the afternoon to avoid throwing them away."
   Example: "Loss Warning: Throwing away 10 items daily equals losing roughly ₹150-₹200 in profit."

Keep the language simple, encouraging, and easy for a street vendor to understand.
Return ONLY the bullet point lines, nothing else. No intro, no outro.
""".strip()

    response = llm.invoke(prompt)
    insights_text = response.content.strip()
    insights = [line.strip().lstrip('•*- ') for line in insights_text.splitlines() if line.strip()]

    return {**state, "analysis": insights_text, "waste_insights": insights}

def output_node(state: WasteState) -> WasteState:
    print("\n" + "═" * 55)
    print("   🗑️  WASTE & LOSS INSIGHTS")
    print("═" * 55)
    for line in state["waste_insights"]:
        print(f"  • {line}")
    print("═" * 55 + "\n")
    return state

# ─────────────────────────────────────────
# GRAPH BUILDER
# ─────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(WasteState)
    
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

    initial_state: WasteState = {
        "vendor_id": "69c7ee1bb5546e91df1818eb",
        "raw_data": [],
        "analysis": "",
        "waste_insights": [],
    }

    # If running locally to test
    final_state = asyncio.run(app.ainvoke(initial_state))