import json
from schemas.state import State
from llm import llm
from langchain_core.messages import AIMessage
from tools.lang import get_vendor_language

async def recommender(state: State):
    print("--- EXECUTING RECOMMENDER NODE ---")

    # 1. Get the original user message
    msg_content = state["messages"][0].content

    # 2. Parse the JSON string from query_checker to get missing fields
    last_msg_content = state["messages"][-1].content
    try:
        parsed = json.loads(last_msg_content)
        missing_fields = parsed.get("missing", ["unknown_field"])
    except (json.JSONDecodeError, AttributeError):
        missing_fields = ["unknown_field"]

    print("Missing fields:", missing_fields)

    # 3. Pull vendor's real item catalog from state (set by get_vendor_attributes)
    vendor_attributes = state.get("vendor_attributes", {})
    item_catalog = vendor_attributes.get("itemCatalog", [])
    vendor_name = vendor_attributes.get("vendorName", "the vendor")

    # 4. Serialize catalog and missing fields for injection into prompt
    item_catalog_str = json.dumps(item_catalog, indent=2) if item_catalog else "No catalog available."
    missing_fields_str = ", ".join(missing_fields)
    lang = await get_vendor_language(state["vendor_id"])
    print(lang)
    # 5. System prompt with all variables properly injected
    system_prompt = f"""You are a retail transaction assistant embedded in a POS system.
Your job is to intelligently infer missing transaction details using structured catalog data.

Vendor: {vendor_name}

Missing Fields: {missing_fields_str}

Item Catalog:
{item_catalog_str}

Partial Transaction Context: '{msg_content}'

Your task:
- Analyze the catalog and context above
- Suggest 1–3 highly relevant completions ONLY for the missing fields listed
- Rules:
  • Only use items from the catalog above
  • Infer price from sellingPrice if the amount field is missing
  • Suggest practical quantities (1, 2, 3, 5, etc.) if quantity is missing
  • Do not invent items not present in the catalog

Output Format:
- A JSON list of casual, conversational confirmation strings
- Each string should sound like a friendly cashier asking "did you mean...?"
- Fill in ALL missing fields naturally within the sentence
- Use "rs" for currency, keep it short and informal
- No explanations, no markdown, no extra formatting
- Example: ["did you mean you sold milk 2 quantities for 45 rs?", "did you mean you sold 1 pack of bread for 30 rs?"]
give ans in whatever lang user wants i.e{lang}
Focus on accuracy, realism, and contextual relevance."""

    # 6. Construct message payload — system + human turn
    messages_to_pass = [
        ("system", system_prompt),
        ("human", f"Based on the context and catalog, suggest completions for the missing fields: {missing_fields_str}"),
    ]

    # 7. Invoke LLM
    response = llm.invoke(messages_to_pass)

    # 8. Ensure response content is a plain string before wrapping
    raw_content = response.content if hasattr(response, "content") else str(response)

    # 9. Validate that the LLM returned parseable JSON; log a warning if not
    try:
        parsed_response = json.loads(raw_content)
        if not isinstance(parsed_response, list):
            print("Warning: LLM response is valid JSON but not a list:", parsed_response)
    except json.JSONDecodeError:
        print("Warning: LLM response is not valid JSON. Raw output:", raw_content)

    # 10. Wrap in AIMessage for consistent graph state handling
    return {"messages": [AIMessage(content=raw_content)]}