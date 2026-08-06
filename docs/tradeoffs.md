# Tradeoffs — Every Major Tech Choice, Pros/Cons/Alternatives

Format per tool: what it's actually doing in *this* codebase, then the generic
pros/cons/alternatives an interviewer expects.

---

## FastAPI

**In this codebase**: `api.py` — three main routes, two of which stream results back over
Server-Sent Events (`StreamingResponse(generate_response(), media_type="text/event-stream")`)
so the client gets incremental status updates (`"Analyzing audio..."` → `"fast_text"` →
`"AI Agent processing..."` → `"complete"`) instead of waiting on one big blocking response.

- **Pros**: Native `async def` support pairs directly with Motor (async Mongo driver) and
  `asyncio.to_thread` for the CPU-bound Whisper calls — no event-loop blocking. Automatic
  request validation via Pydantic (`AgentQuery` model). `StreamingResponse` makes SSE trivial,
  which matters a lot here since the whole UX is "show progress while a multi-second
  pipeline runs."
- **Cons**: SSE via `StreamingResponse` is one-directional — if this product ever needs the
  client to interrupt/cancel a long-running agent turn mid-stream, you'd need WebSockets
  instead. No built-in retry/backpressure handling for slow clients. Error handling inside a
  streaming generator is awkward (can't raise `HTTPException` after streaming has started —
  see `failure_cases.md`).
- **Alternatives**: Flask (simpler, but async story is bolted-on, worse fit for Motor/Whisper
  concurrency here); Express/Node (would unify with the existing Node.js internal service
  seen in `save_transaction.py`, removing a cross-language hop, but loses the Python-native
  LangGraph/Whisper/OpenAI ecosystem this whole pipeline is built on — not a real option given
  the stack). Django + Channels (heavier than needed for a handful of routes).

## LangGraph

**In this codebase**: Three graphs — one real branching state machine
(`text_db_agent.py`: classify → validate → extract-or-clarify) and two linear pipelines
(`next_day_agent.py`, `waste_agent.py`).

- **Pros**: Conditional edges (`add_conditional_edges`) make the classify→validate→branch
  logic explicit and inspectable (`graph.get_graph().draw_mermaid_png()` is literally called
  at import time to visualize it) instead of nested `if/elif` spaghetti across multiple LLM
  calls. `MemorySaver` + `thread_id` gives multi-turn conversation memory "for free" without
  hand-rolling a session store. Each node is a small, independently-testable function.
- **Cons**: Real learning curve/boilerplate for what is, in the transaction graph's case,
  only 4 decision points — a simpler orchestration (a plain Python function with `match`/`if`
  calling the same LLM helper functions) would have fewer moving parts for something this
  size. The checkpointer story is deceptively easy to get *wrong in production* (see
  `MemorySaver` being in-memory-only in `failure_cases.md`/`workflow.md`) — LangGraph makes
  persistence *possible* but doesn't force you to pick a real backend, so it's easy to ship
  the in-memory default and only discover the gap under multi-worker deployment.
- **Alternatives**: Plain function orchestration (less overhead, but loses graph
  visualization and built-in checkpointing — you'd hand-roll both). CrewAI/AutoGen
  (multi-agent framing is heavier than needed here — this isn't really multiple autonomous
  agents negotiating, it's a deterministic pipeline with one branch point, which is exactly
  LangGraph's sweet spot rather than overkill). Temporal/durable-execution engines (genuinely
  better for the "conversation must survive process restarts" requirement this app actually
  has, but a much bigger infra commitment than swapping a checkpointer backend).

## Whisper (local, dual-pass: base + turbo)

**In this codebase**: `tools/sp_text.py` loads *two* local Whisper models at startup
(`base` and `large-v3-turbo`) and `api.py` runs both per request — base first for instant
feedback, turbo second for the accurate transcript that actually feeds the agent.

- **Pros**: Fully local/offline — no per-request API cost, no network dependency on a
  third-party STT vendor, and no audio data leaving the server (relevant for a
  vendor-financial-data product). The two-pass design is a genuinely good UX trick: the user
  sees *something* on screen almost immediately while the slower, better model still runs in
  the background.
- **Cons**: Running two model inference passes per request is expensive in latency and
  compute compared to sending audio to one hosted STT API — both models are loaded into
  memory permanently (`model_base` and `model_turbo` both resident), which is a meaningful
  fixed memory/GPU-or-CPU cost regardless of traffic. `task="translate"` forces everything to
  English output, which is a deliberate simplification (downstream prompts assume English)
  but means the *original* language nuance/slang is lost before the LLM ever sees it — the
  language personalization elsewhere (`get_vendor_language`) only affects *output* language,
  not what the transcription step "hears."
- **Alternatives**: A hosted STT API (Deepgram, AssemblyAI, Google Speech-to-Text, or OpenAI's
  own `whisper-1`/`gpt-4o-transcribe` endpoints) — trades local-compute cost and data
  residency for per-request latency+$ and an external dependency, but removes the "load two
  multi-GB models into every server instance" operational burden entirely. Given this product
  is voice-first for a specific accent/language population (Hinglish, per the classifier's
  examples), a strong argument exists either way: local Whisper lets you fine-tune/pick model
  size freely; a hosted API removes ops burden but you're at the mercy of its accent coverage.

## OpenAI (`gpt-4.1-mini`, via LangChain's `ChatOpenAI`)

**In this codebase**: `llm.py` — every agent node shares one `llm` instance, `temperature=0`,
used both for plain `.invoke()` calls and via `.with_structured_output(SchemaClass)`.

- **Pros**: `temperature=0` is the right call for classification/extraction/validation tasks
  where you want deterministic, repeatable behavior, not creative variance. `with_structured_output`
  leans on OpenAI's native function-calling/tool-schema support, which is more reliable than
  prompting for JSON and regex-parsing it (see `prompts.md`). `gpt-4.1-mini` is a reasonable
  cost/quality point for high-volume, low-complexity classification tasks (this pipeline
  makes *four to five* separate LLM calls per single user message — classify, validate,
  extract or recommend — so per-call cost matters a lot here).
  - **Note**: A `ChatGroq` (Llama 3.1 8B) import is commented out in `llm.py` — evidence this
    was actually A/B'd or migrated away from at some point, which is worth mentioning if asked
    "why this model" — you can honestly say "the code shows they evaluated a cheaper/faster
    open-weight option via Groq and moved to OpenAI," even without knowing their exact reason.
- **Cons**: Every request costs 4-5 sequential LLM round trips (classify → validate →
  extract/recommend, plus a possible `get_vendor_attributes` pre-fetch) — this is a latency
  and cost multiplier that a single well-crafted multi-task prompt could reduce, at the cost
  of losing the clean separation-of-concerns (see `prompts.md`'s point on why validation and
  extraction are deliberately split). No caching layer — identical/near-identical messages
  re-run the full pipeline every time.
- **Alternatives**: Groq-hosted Llama (much cheaper/faster inference, open-weights, but likely
  weaker structured-output reliability and reasoning quality for the nuanced
  "service-vs-physical-good quantity" type judgment calls in the validator prompts — a real
  quality/cost tradeoff, not a strict downgrade). Anthropic Claude (comparable structured
  output support, would be a reasonable swap). Self-hosted fine-tuned small model (would only
  make sense at very high volume, given how narrow/repetitive these classification tasks are —
  a fine-tuned model in the 1-3B range could likely replace several of these calls at a
  fraction of the cost, once you have training data from real production usage to fine-tune on).

## MongoDB (via Motor, async driver)

**In this codebase**: `db.py` — single global `AsyncIOMotorClient`, collections for
`dailyrecords`, `saleevents`, `recommendations`, `vendors`, `insights`.

- **Pros**: Schema flexibility fits this domain well — `dailyrecords` documents have
  variable-shape arrays (`itemsSold`, `unsoldItems`, `wastedItems`) that would require more
  ceremony (junction tables, nullable columns) in a rigid relational schema. Motor's async
  API is a clean fit with FastAPI's `async def` routes — no thread pool needed for DB calls
  the way a sync driver would require. Document-per-day (`dailyrecords`) maps naturally onto
  the "aggregate by day, then by week" access pattern the next-day/waste agents use.
- **Cons**: No transactions being used here despite genuinely transactional-sounding data
  (money) — `save_sale_event`'s Mongo write and the Node.js notification call aren't wrapped
  in any consistency guarantee, and there's no multi-document transaction even around the
  Mongo write itself if it ever needs to touch more than one collection atomically. No schema
  validation at the DB layer — correctness is entirely dependent on the Pydantic schemas
  upstream in `schemas/transactions.py`, and nothing stops a bad direct Mongo write elsewhere
  in the app from violating those assumptions later.
- **Alternatives**: PostgreSQL + JSONB columns (would get relational integrity/transactions
  for the money-critical parts *and* keep flexible-array storage for the variable item lists
  — arguably a better fit given this data is financial, not just for reporting). A hybrid
  (Postgres for `saleevents`/ledger data, Mongo/JSON for `dailyrecords` aggregation) is
  another reasonable middle ground, at the cost of running two databases.

## SQL vs. NoSQL specifically (since this product is financial)

- **Why NoSQL was likely chosen**: Fast iteration during early product development — schemas
  visibly evolved (`transaction_type` uses a `Literal` with 7 values but only 3 are
  reachable through the current classifier; `personName`/`expenseType` are type-specific
  optional fields) which is much cheaper to iterate on in Mongo than via SQL migrations.
- **Where it costs them**: Financial ledger data (`saleevents`, implicitly udhar/expense
  records) is exactly the kind of data that benefits most from ACID guarantees, foreign-key
  integrity (does `vendorId` in `saleevents` actually always point to a real vendor?), and
  `SUM`/`GROUP BY` aggregate queries — which `next_day_agent.py` and `waste_agent.py`
  currently do **in the LLM prompt** (dumping 7 days of records as text and asking the model
  to "identify trends") instead of a `GROUP BY item, SUM(quantity)` query, which would be
  cheaper, deterministic, and faster than delegating arithmetic to an LLM.

## Vector DB / RAG — notably absent

**In this codebase**: No embeddings, no vector store, anywhere. All "context" the LLM gets is
either (a) freshly queried structured Mongo data serialized into the prompt (`vendor_attributes`,
`raw_data`), or (b) the current conversation's `messages` list.

- **Why that's the right call here**: There's no unstructured knowledge base to retrieve from
  — vendor catalogs, sales history, and financial averages are all small, structured, and
  cheap to fetch directly and inject wholesale into a prompt. RAG solves "too much
  unstructured text to fit in context, need to retrieve the relevant slice" — that problem
  doesn't exist in this domain (a vendor's catalog is a handful of items, 7 days of records is
  a few KB of text). Reaching for a vector DB here would be solving a problem this product
  doesn't have.
- **When it would start to matter**: If the product added a "search past transactions in
  natural language across months of history" feature, or a knowledge base of tax/regulatory
  advice per region, *then* RAG would earn its complexity. Good to preempt this question by
  explaining why it's absent rather than letting it look like an oversight.

## Fine-tuning — also absent, and correctly so (for now)

- **Why not fine-tuned**: Three tightly-scoped, few-shot-prompted classification/extraction
  tasks running on `gpt-4.1-mini` at presumably modest volume don't yet justify the
  fixed cost of curating a fine-tuning dataset, retraining, and re-validating quality —
  prompting + `with_structured_output` gets ~90% of the benefit at ~0% of the upfront cost.
- **When it would start to matter**: Once there's a large corpus of real production
  transcripts + corrected labels (e.g., every time a user's clarification response effectively
  "corrects" what the classifier/validator originally guessed), that's exactly the training
  signal you'd want to fine-tune a small, cheap, low-latency model on — a natural
  "phase 2" answer to "how would you reduce the 4-5-calls-per-message cost."

## Flask / Express — considered and rejected implicitly

Already covered under FastAPI above — worth having one crisp line ready: *"Flask would've
worked but async Mongo + concurrent Whisper calls + SSE streaming all favor FastAPI's native
async support; Express would unify the language with the existing Node.js internal service,
but this whole pipeline (LangGraph, Whisper, OpenAI SDK) is Python-native, so switching
languages isn't really on the table without a full rewrite."*