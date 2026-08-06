# Workflow — The Actual Graph(s)

There are **three independent LangGraph workflows** in this codebase. Only one is conversational and contains real branching. The other two are simple analytical pipelines.

A common interview question is:

> **"Walk me through your LangGraph architecture."**

The correct answer is that **each workflow is a separate graph because each solves a different problem with a different lifecycle.**

* The **transaction graph** is conversational, stateful, and requires conditional routing and checkpointing.
* The **next-day suggestion graph** is a one-shot analytics pipeline.
* The **waste insight graph** is another one-shot analytics pipeline.

Keeping them separate has several benefits:

* Each graph has a much smaller state object.
* Nodes only depend on data relevant to that workflow.
* Independent testing becomes easier.
* Stateless workflows don't pay the complexity cost of checkpointing.
* Future changes to one workflow don't affect unrelated pipelines.

A single giant graph would unnecessarily couple unrelated workflows and create one large state object carrying fields that most nodes never use.

---

# How State Flows

Every node receives the current **State** object and returns **only the fields it modifies**.

LangGraph automatically merges those returned fields into the shared state before executing the next node.

```
State
  │
  ▼
Node A
returns {"query_type": "sale"}

State (merged)
  │
  ▼
Node B
returns {"validation": {...}}

State (merged)
  │
  ▼
Node C
...
```

Nodes never call each other directly.

The **State object is the communication mechanism** between nodes.

---

# 1. Transaction Logging Graph (`agents/text_db_agent.py`)

This is the primary workflow and the only graph with conditional routing.

```
START
  │
  ▼
Query Type Checker
  │
  ▼ route_by_type()
  ├────────► Sale Validator
  ├────────► Expense Validator
  └────────► Udhar Validator

Sale Validator
  │
  ▼ route_query()
  ├────────► Sale Query Generator ─────► END
  └────────► Recommendation Engine ────► END

Expense Validator
  │
  ▼ route_query()
  ├────────► Expense Query Generator ──► END
  └────────► Recommendation Engine ────► END

Udhar Validator
  │
  ▼ route_query()
  ├────────► Udhar Query Generator ────► END
  └────────► Recommendation Engine ────► END
```

The graph contains:

* 9 executable nodes
* 4 conditional routing decisions
* no cycles
* one validation path per execution
* every path eventually reaches `END`

---

# Why classify first?

Instead of prompting one LLM with a massive prompt capable of understanding every transaction type, the workflow first classifies the request into:

* sale
* expense
* udhar

Each validator therefore receives a much narrower prompt.

Benefits:

* smaller prompts
* simpler schemas
* better structured output
* easier maintenance
* easier prompt tuning
* lower hallucination risk

The classifier acts as a dispatcher that sends the request into the correct specialized pipeline.

---

# Why separate Validator and Recommendation Engine?

The validator has exactly one responsibility:

> Determine whether all required information is present.

It should **not** generate clarification questions.

If information is missing, responsibility shifts to the Recommendation Engine.

```
Validator
↓

missing fields?

↓

Recommendation Engine
↓

generate clarification questions
```

This separation follows the Single Responsibility Principle.

Benefits:

* smaller prompts
* independent testing
* reusable recommendation logic
* easier prompt improvements

---

# Conditional Edge 1 — Dispatcher

```python
graph_builder.add_conditional_edges(
    "Query Type Checker",
    route_by_type,
    {
        "sale": "Sale Validator",
        "expense": "Expense Validator",
        "udhar": "Udhar Validator",
    },
)
```

The classifier returns structured JSON.

Example:

```json
{
    "transaction_type":"sale"
}
```

`route_by_type()` reads this output and chooses the next validator.

---

## Fail-open behaviour

If the classifier returns malformed JSON,

```python
json.JSONDecodeError
```

the router defaults to

```
sale
```

instead of crashing.

This is an intentional **fail-open** design.

Tradeoff:

Advantages

* workflow continues
* user still receives a response
* avoids complete failure

Disadvantages

* transaction may be silently misclassified

This is worth mentioning in interviews because it shows awareness of reliability vs correctness tradeoffs.

---

# Conditional Edge 2–4 — Validator Routing

Each validator has identical routing logic.

```python
graph_builder.add_conditional_edges(
    "Sale Validator",
    route_query,
    {
        "correct":"Sale Query Generator",
        "incorrect":"Recommendation Engine",
    },
)
```

The Expense and Udhar validators use the same pattern.

Validators return structured JSON.

Example

```json
{
    "flag":"correct",
    "missing":[]
}
```

or

```json
{
    "flag":"incorrect",
    "missing":[
        "quantity"
    ]
}
```

`route_query()` simply reads `"flag"`.

```
correct

↓

Query Generator
```

or

```
incorrect

↓

Recommendation Engine
```

---

# Latent Bug

`route_query()` also contains another return path.

If JSON parsing fails, it returns

```
invalid
```

However,

```
invalid
```

does **not** exist in the edge mapping.

Therefore LangGraph cannot find the next node and raises a runtime error.

Current mapping:

```
correct
incorrect
```

Possible runtime return:

```
invalid
```

This is a genuine latent bug and a good failure case to discuss during interviews.

Possible fixes:

* add an `"invalid"` edge
* retry parsing
* send invalid responses to Recommendation Engine
* raise a custom error node

---

# Deterministic Routing vs LLM Nodes

Not every node calls an LLM.

LLM-powered nodes:

* Query Type Checker
* Sale Validator
* Expense Validator
* Udhar Validator
* Sale Query Generator
* Expense Query Generator
* Udhar Query Generator
* Recommendation Engine

Deterministic Python components:

* `route_by_type()`
* `route_query()`

Once an LLM produces structured output, the workflow routing itself is entirely deterministic.

---

# Loops

There are **no graph cycles**.

Every execution is acyclic.

```
START

↓

...

↓

END
```

This is intentional.

Adding graph-level retry loops would repeatedly invoke LLMs, complicate termination, and increase token usage.

Instead, clarification is handled outside the graph.

---

# External Conversation Loop

When required fields are missing,

```
Recommendation Engine
```

returns clarification questions.

The API stores them in MongoDB and returns them to the frontend.

The user replies.

The frontend sends a **new API request** using the same `thread_id`.

A completely new graph execution begins.

```
Request 1

START

↓

END

↓

User replies

↓

Request 2

START

↓

END
```

This is **not** a graph loop.

It is **multiple independent graph executions** sharing conversation history through checkpointing.

---

# Retries

There are **no retries inside LangGraph.**

The only retry-like behaviour is the dual Whisper transcription strategy.

```
speech_to_text_base()

↓

fast response

↓

speech_to_text_turbo()

↓

higher accuracy
```

This is not a retry because both models intentionally execute.

The second model exists to improve transcription quality.

---

# Fallback Behaviour

### Query Type Checker

Malformed JSON

↓

defaults to

```
sale
```

---

### Speech Endpoint

If Turbo Whisper returns nothing,

the API falls back to

```
fast_text
```

generated by the base Whisper model.

---

### Recommendation Engine

If the LLM fails to return valid JSON,

the node logs the issue and returns the raw string.

Later,

`main()` safely executes

```python
try:
    suggestions = json.loads(raw_content)
except:
    suggestions = [raw_content]
```

The fallback therefore exists one layer above the node rather than inside the node itself.

---

# 2. Next-Day Suggestion Graph (`agents/next_day_agent.py`)

```
START

↓

fetch_data

↓

agent

↓

output

↓

END
```

This workflow is completely linear.

No branching.

No checkpointing.

No conditional edges.

`fetch_data`

* retrieves seven days of daily records
* loads vendor language

`agent`

* calls the LLM
* predicts tomorrow's inventory quantities

`output`

* prints formatted output
* API returns `final_state["suggestions"]`

---

# 3. Waste Insight Graph (`agents/waste_agent.py`)

```
START

↓

fetch_data

↓

agent

↓

output

↓

END
```

Graph topology is identical.

Inside `agent_node()` there is one normal Python guard clause.

```
if no waste history:

    return "Great job!"
```

Instead of calling the LLM.

Notice this is **not** a LangGraph branch.

It is simply ordinary Python.

This demonstrates that not every decision needs to become a graph edge.

If no downstream routing changes, a simple guard clause is often the cleaner solution.

---

# Compilation

```python
memory = MemorySaver()

graph = graph_builder.compile(
    checkpointer=memory
)
```

Compilation converts the graph definition into an executable workflow.

After compilation:

* node definitions are fixed
* edge topology is fixed
* execution can begin

Changing nodes or edges requires rebuilding and recompiling the graph.

---

# Checkpointing

Only the transaction graph uses checkpointing.

```
MemorySaver()

↓

thread_id

↓

conversation history
```

Reason:

The transaction workflow supports multi-turn clarification conversations.

The other two graphs are one-shot analytical pipelines.

Each API request simply builds a fresh graph.

No conversation memory is required.

---

# Interview Framing

If an interviewer says:

> "Draw your graph."

Draw the transaction graph.

Then proactively mention these architectural points:

1. Three independent graphs instead of one giant graph.
2. Classification before validation reduces prompt complexity.
3. Validators only validate.
4. Recommendation Engine generates clarification.
5. State is the communication mechanism between nodes.
6. Routing functions are deterministic Python.
7. There are no graph loops—clarification is implemented as multiple graph executions sharing checkpoints.
8. The classifier fails open by defaulting to `"sale"`.
9. There is a latent `"invalid"` routing bug worth fixing.
10. Only the transaction graph requires checkpointing because only it is conversational.

Those design decisions demonstrate understanding of **LangGraph architecture**, not just the ability to assemble nodes.
