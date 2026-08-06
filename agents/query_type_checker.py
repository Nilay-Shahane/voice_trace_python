import json
from schemas.transaction_type import TransactionType
from schemas.state import State
from llm import llm
from langchain_core.messages import AIMessage


def query_type_checker(state: State):
    msg_content = state['messages'][0].content

    prompt = f'''Task

                    Classify the user's business transaction into exactly one label.

                    Labels

                    sale
                    The business receives money by providing goods or services.

                    expense
                    The business spends money to acquire goods, services, inventory, or operating costs.

                    udhar
                    The transaction creates, updates, settles, or refers to a credit/debt relationship where payment is deferred.

                    Rules

                    - Interpret every message from the business owner's perspective.
                    - Focus on transaction intent, not keywords.
                    - Messages may be in English, Hindi, Marathi, or mixed languages.
                    - Ignore spelling mistakes and informal wording.
                    - If a sale is made on credit, classify as "udhar".
                    - Return exactly one lowercase label:
                    sale
                    expense
                    udhar

                    Examples:
                    - "I sold 2 pizzas for 80 rs"           → sale
                    - "I spent 150 on an auto"              → expense
                    - "Paid shop rent 5000"                 → expense
                    - "Rahul took 500 on udhar"             → udhar
                    - "I gave 200 to Suresh on credit"      → udhar
                    - "Becha 3 samose 30 mein"              → sale

                    User Message: "{msg_content}"
                    '''

    messages_to_pass = [
        ("system", prompt),
        ("human", msg_content)
    ]

    check_llm = llm.with_structured_output(TransactionType)
    parsed_check = check_llm.invoke(messages_to_pass)

    print(f"Transaction type detected: {parsed_check.model_dump_json()}")
    return {
        "messages": [AIMessage(content=parsed_check.model_dump_json())],
        "original_input": msg_content,  # set once here, never overwritten
    }


def route_by_type(state: State) -> str:
    last_message = state['messages'][-1].content

    try:
        type_data = json.loads(last_message)
        intent = type_data.get('transaction_type', type_data.get('type', '')).lower().strip()

        if intent in ['sale', 'expense', 'udhar']:
            print(f"Routing to: {intent}")
            return intent

        print(f"WARNING: Unexpected transaction type '{intent}', defaulting to 'sale'")
        return 'sale'

    except json.JSONDecodeError:
        print("ERROR: Could not decode JSON in route_by_type. Raw content:", last_message)
        return 'sale'