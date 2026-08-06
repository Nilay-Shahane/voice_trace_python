# State Management — Deep Dive (Interview Notes)

One of the biggest concepts in LangGraph is **State**.

Think of State as the **shared memory of a graph**.

Every node receives the current state, performs some work, and returns only the fields it wants to update. LangGraph merges those updates back into the state before executing the next node.

Unlike a normal Python function where you pass arguments from function to function, LangGraph uses a **central immutable-ish state object** that evolves throughout execution.

---

# Why Three Different State Objects?

This project has **three completely separate graphs**, therefore **three different state schemas**.

This is intentional.

Each graph has a different purpose, different nodes, and different lifecycle.

```
Transaction Graph
      │
      ▼
 State

Next Day Prediction Graph
      │
      ▼
VendorState

Waste Insight Graph
      │
      ▼
WasteState
```

### Why not one giant state?

Interviewers love asking this.

A huge shared state is actually considered bad design.

Reasons:

- Nodes become coupled to unrelated fields.
- Difficult to understand which node owns which data.
- Easier to accidentally mutate fields.
- Harder to test nodes independently.
- Violates Separation of Concerns.

A graph should only carry data required by **its own nodes**.

Every graph is basically its own mini application.

---

# LangGraph Execution Model

Every node follows the exact same pattern.

```
Incoming State
       │
       ▼
+----------------+
|     Node       |
+----------------+
       │
Returns Updated Fields
       │
       ▼
LangGraph merges updates
       │
       ▼
Next Node
```

Example

```python
state = {
    "vendor_id": "...",
    "messages": [...]
}
```

Node returns

```python
{
    "analysis": "User bought 5 apples"
}
```

LangGraph internally produces

```python
{
    "vendor_id": "...",
    "messages": [...],
    "analysis": "User bought 5 apples"
}
```

The node never needs to manually copy the old state.

Only changed fields are returned.

---

# Reducers in LangGraph

Normally, if two nodes return

```python
{
    "messages": [...]
}
```

the second node would overwrite the first.

Sometimes we don't want replacement.

We want accumulation.

That's exactly what reducers do.

This project uses

```python
Annotated[list, add_messages]
```

instead of

```python
messages: list
```

Meaning

```
Old messages
     +
New messages
     =
Merged conversation
```

instead of

```
Old messages

↓

Deleted

↓

New messages
```

Without `add_messages`, every node would erase conversation history.

---

# State 1 — Transaction Graph

Location

```
schemas/state.py
```

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]
    recent_msg: str
    vendor_id: str
    vendor_attributes: dict
```

This state powers

```
text_db_agent.py
```

Pipeline

```
START
   │
   ▼
Query Type
   │
   ▼
Validation
   │
   ├──────────────┐
   ▼              ▼
Extraction    Recommendation
   │              │
   └──────► END ◄─┘
```

---

# messages

```python
messages: Annotated[list, add_messages]
```

## Purpose

Stores the entire conversation.

This is the most important field.

Instead of passing outputs manually between nodes, every node simply appends a message.

Think of it as the graph's memory.

---

## Why Annotated?

```python
Annotated[list, add_messages]
```

means

> Whenever a node returns `"messages"`, append it instead of replacing it.

Without it

```
Node A

messages:
User

↓

Node B

messages:
Classifier

↓

User lost
```

With reducer

```
User

↓

Classifier

↓

Validator

↓

Extractor
```

Everything stays.

---

## Who writes it?

Every node.

### query_type_checker

Returns

```python
{
    "messages": [
        AIMessage(content='{"transaction_type":"sale"}')
    ]
}
```

---

### query_checker_sale

Returns

```python
{
    "messages":[
        AIMessage(
            content='{"flag":"complete"}'
        )
    ]
}
```

---

### recommender

Returns

```python
{
    "messages":[
        AIMessage(
            content='["Which customer?"]'
        )
    ]
}
```

---

### db_query_maker

Returns

```python
{
    "messages":[
        AIMessage(
            content='{"item":"Milk"}'
        )
    ]
}
```

---

## Who reads it?

Mostly routing functions.

Example

```python
state["messages"][-1].content
```

is used by

```
route_by_type()

route_query()
```

because the latest message contains

```
transaction_type

or

validation result
```

The extraction nodes also use it.

Example

```python
messages[0]
```

to recover the original user prompt.

---

## Lifecycle

Starts with

```python
graph.astream({
    "messages":[HumanMessage(content=voice_text)]
})
```

After classification

```
Human
Classifier
```

After validation

```
Human
Classifier
Validator
```

After extraction

```
Human
Classifier
Validator
Extractor
```

Every hop adds one AIMessage.

---

## MemorySaver Interaction

The graph uses

```
MemorySaver
```

which checkpoints state using

```
thread_id
```

So

```
Turn 1

↓

Messages stored

↓

Turn 2

↓

Messages loaded

↓

Continue
```

instead of starting empty.

This enables multi-turn conversations.

---

## Important Caveat

Many extraction nodes read

```python
messages[0]
```

assuming it is the current user input.

That assumption is only true on the **first invocation**.

Suppose

```
Turn 1

"I sold apples"

↓

Need clarification

↓

Turn 2

"To Rahul"
```

MemorySaver reloads previous messages.

Now

```
messages[0]
```

still contains

```
"I sold apples"
```

not

```
"To Rahul"
```

If your extraction node expects the newest user message from `messages[0]`, it will be wrong.

A safer approach is to store the current input explicitly (for example `recent_msg`) or search for the latest `HumanMessage`.

This is a subtle but excellent interview discussion point.

---

# recent_msg

```python
recent_msg: str
```

Purpose

Current user input only.

Unlike

```
messages
```

this field never accumulates.

Each invocation simply replaces it.

---

## Why have it?

Sometimes the validator only needs

```
latest message
```

not the entire conversation.

Using a string is

- simpler
- smaller
- faster

than traversing message history.

---

## Written by

Initial graph invocation

```python
{
    "recent_msg": voice_text
}
```

---

## Read by

Currently

```
query_checker_sale
```

---

## Lifecycle

```
Input

↓

Stored

↓

Read once

↓

Never changed
```

---

# original_input Inconsistency

One interesting issue exists.

Some validators use

```python
state["recent_msg"]
```

Others use

```python
state["original_input"]
```

But

```python
original_input
```

is not declared inside

```python
State
```

It is dynamically injected.

Example

```python
return {
    "original_input": ...
}
```

TypedDict does **not** enforce fields at runtime.

So Python happily accepts it.

Technically

```
State schema

≠

Actual runtime state
```

This is a maintainability smell.

A cleaner design would standardize on a single field (e.g., `recent_msg`) and declare it explicitly in the schema.

---

# vendor_id

```python
vendor_id: str
```

Purpose

Primary identifier of the logged-in vendor.

Acts as the join key across MongoDB collections.

Example

```
vendors

dailyrecords

saleevents

recommendations

insights
```

All are connected through

```
vendor_id
```

---

## Written by

API layer

```python
vendor_id=user_id
```

before graph execution.

---

## Read by

Inside graph

```
recommender
```

Outside graph

```
get_vendor_attributes()

save_transaction()
```

---

## Lifecycle

```
API

↓

Graph

↓

Database
```

Never changes.

---

## Possible Improvement

Validate

```python
ObjectId
```

at the API boundary.

Currently malformed IDs fail much deeper inside Mongo/BSON utilities, making debugging harder.

---

# vendor_attributes

```python
vendor_attributes: dict
```

Purpose

Provides business context to the LLM.

Instead of hallucinating,

the model knows

- vendor name
- catalog
- prices
- margins
- popular products

---

## Written by

Outside the graph.

```python
vendor_attributes =
await get_vendor_attributes(...)
```

Then injected into state.

---

## Why outside the graph?

Because

- fetched once
- never changes
- every node doesn't need it

Creating an additional node would only increase graph complexity.

Current design

```
DB Fetch

↓

Graph Starts
```

instead of

```
Graph

↓

Fetch Node

↓

Next Node
```

Less orchestration overhead.

---

## Read by

Only

```
recommender
```

---

## Tradeoff

Even if validation succeeds immediately,

```
vendor_attributes
```

is still fetched.

Meaning

```
Extra Mongo query

↓

Unused

↓

Request completes
```

Could be optimized using lazy loading or a dedicated node executed only when recommendations are needed.

---

# State Lifecycle (Transaction Graph)

```
API

↓

Create State

↓

messages
recent_msg
vendor_id
vendor_attributes

↓

Classifier

↓

Validator

↓

Extraction
or
Recommendation

↓

END

↓

Save Transaction
```

---

# State 2 — VendorState (Next-Day Suggestions)

Location

```
schemas/vendor.py
```

```python
class VendorState(TypedDict):
    vendor_id: str
    raw_data: list
    analysis: str
    suggestions: List[str]
    lang: str
```

Graph

```
START

↓

Fetch Data

↓

LLM Analysis

↓

Output

↓

END
```

No branching.

Linear pipeline.

---

# vendor_id

Used by

```
fetch_data_node
```

to retrieve

```
dailyrecords
```

for that vendor.

---

# raw_data

Filled by

```
fetch_data_node
```

Contains

```
7 days

Sales

Waste

Unsold

Inventory
```

before LLM analysis.

---

## Why serialize Mongo data?

Mongo returns objects like

```python
ObjectId(...)
datetime(...)
```

LLMs expect plain text.

Convert to

```python
str()
```

or JSON first.

Otherwise prompt construction fails.

---

# lang

Fetched from

```
get_vendor_language()
```

Used to force

```
Hindi

Marathi

English

...
```

responses.

Without it,

LLM may answer in English by default.

---

# analysis

Raw LLM paragraph.

Intermediate output before formatting.

---

# suggestions

Final cleaned list.

Example

```python
[
"Prepare 20 Samosas",
"Reduce Tea by 5 cups"
]
```

Returned by API.

---

# State Flow

```
vendor_id

↓

Fetch Data

↓

raw_data

↓

LLM

↓

analysis

↓

Parser

↓

suggestions
```

---

# State 3 — WasteState

```python
class WasteState(TypedDict):
    vendor_id: str
    raw_data: list
    analysis: str
    waste_insights: List[str]
```

Very similar to VendorState.

Pipeline

```
START

↓

Fetch Waste Data

↓

LLM

↓

Output

↓

END
```

---

# Difference from VendorState

No

```python
lang
```

field.

Meaning waste insights are currently **not localized**.

This is a consistency gap.

A future improvement would be to reuse the same localization mechanism as the next-day recommendation graph.

---

# Comparison of All States

| State | Graph | Branching | Purpose |
|---------|---------|------------|------------|
| `State` | Transaction Logging | ✅ Yes | Classify, validate, extract, recommend |
| `VendorState` | Next-Day Suggestions | ❌ No | Analyze historical sales and suggest tomorrow's inventory |
| `WasteState` | Waste Insights | ❌ No | Analyze waste trends and generate improvement insights |

---

# Why Not Use Global Variables?

Global variables are problematic because:

- Multiple users would overwrite each other's data.
- Not thread-safe.
- Difficult to scale across workers or servers.
- Impossible to checkpoint and resume.
- Hard to test.

State is passed explicitly through the graph, making execution deterministic and reproducible.

---

# Why TypedDict Instead of Pydantic?

`TypedDict` is lightweight and fits LangGraph's dictionary-based state model.

Advantages:

- No runtime validation overhead.
- Native dictionary semantics.
- Better performance for frequently updated state.
- Excellent editor/type-checking support.

If strong runtime validation is needed, Pydantic models can still be used inside nodes for structured inputs/outputs.

---

# Best Practices Followed

- Separate state per graph.
- Keep only graph-specific fields.
- Use reducers (`add_messages`) only where accumulation is required.
- Treat immutable values (`vendor_id`) as read-only.
- Return only updated fields from nodes.
- Fetch stable context once instead of repeatedly.
- Keep linear graphs simple; reserve richer state for branching workflows.

---

# Improvements I Would Make

1. Remove the `recent_msg` vs `original_input` duplication and standardize on a single field.
2. Add `original_input` (if retained) to the `State` TypedDict so the schema matches runtime behavior.
3. Avoid reading `messages[0]`; instead, store the latest user input explicitly or retrieve the latest `HumanMessage`.
4. Lazily fetch `vendor_attributes` only when the recommender branch executes.
5. Add localization (`lang`) to `WasteState` for consistent multilingual output.
6. Validate `vendor_id` as an `ObjectId` at the API boundary before entering the graph.
7. Consider trimming or summarizing very long `messages` histories when using `MemorySaver` to avoid unbounded growth.

---

# Interview Answer (2 Minutes)

> "LangGraph state is the shared memory passed between every node. I intentionally maintain three separate state objects because each graph has a different lifecycle and should only carry data needed by its own nodes. The transaction graph uses a richer `State` with conversation history, vendor information, and current input because it contains conditional routing and multi-turn clarification. The `messages` field uses LangGraph's `add_messages` reducer so every node appends to the conversation instead of overwriting it. In contrast, the next-day recommendation and waste-analysis graphs are simple linear pipelines, so their states only contain fields like fetched data, intermediate analysis, and final output. This keeps each graph loosely coupled, easier to test, and avoids a large shared state full of unrelated fields. There are a couple of improvements I'd make: unify `recent_msg` and `original_input`, avoid relying on `messages[0]` for multi-turn conversations, lazily fetch vendor attributes only when needed, and add localization support to the waste graph."