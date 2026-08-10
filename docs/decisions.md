# Architecture Decision Q&A — Voice Transaction Agent (Voicetrace)

Interview-ready answers grounded in what the code actually does, not textbook definitions.
Each answer has: **the decision → why → the honest tradeoff / what a reviewer could poke at.**

---

## 1. Why FastAPI over Flask/Django?

**Decision:** FastAPI serves `/api/speech_msg`, `/api/recommend_msg`, `/api/next_day_suggestions`, `/api/waste_insights`.

**Why:**
- The whole pipeline is I/O-bound (Motor async Mongo calls, LLM calls, `asyncio.to_thread` for blocking Whisper inference, `httpx.AsyncClient` calling the Node backend). FastAPI's native `async def` route handlers let one worker handle concurrent requests without threads blocking on network waits — Flask's WSGI model would need gunicorn workers/threads to fake this.
- `StreamingResponse` gives first-class SSE support with almost no boilerplate — needed because the pipeline has multiple sequential stages (audio → fast transcript → accurate transcript → agent status updates → DB save) and the frontend needs progress, not just a final blob.
- Pydantic is baked in, and the same Pydantic models (`SaleTransaction`, `ExpenseTransaction`, `UdharTransaction`) are reused as LangChain structured-output schemas — one model definition, two consumers (API validation + LLM output constraint). That's a real DRY win, not just "FastAPI is trendy."
- `UploadFile`/`Form` gives multipart audio + JSON metadata in one endpoint without manual parsing.

**Tradeoff to admit:** Django would give an admin panel, ORM, auth, migrations "for free" — irrelevant here since Mongo isn't Django's happy path and there's no admin need. Flask + Flask-SSE could technically work but you'd be hand-rolling async support that FastAPI gives natively (Flask 2.x async routes still run in a thread pool under the hood, not true async I/O).

---

## 2. Why LangGraph over a single mega-prompt or plain function chaining?

**Decision:** The pipeline is modeled as an explicit `StateGraph`: `Query Type Checker → (Sale/Expense/Udhar) Validator → route_query → (Query Generator | Recommendation Engine)`.

**Why:**
- This is not one LLM call — it's a **conditional multi-step process with branches and a possible retry loop back to the user** (missing fields → clarification → user replies → re-enter graph). A single prompt can't express "validate, then branch, then either extract or ask for more info" reliably; LangGraph makes that control flow explicit and inspectable (`graph.get_graph().draw_mermaid_png()` literally renders the FSM for debugging).
- Each node does exactly one job (classify type / validate completeness / extract structured fields / recommend missing values) — smaller, single-responsibility prompts are more reliable and easier to unit-test in isolation than one prompt trying to do classification + validation + extraction + clarification at once.
- **State persistence via `MemorySaver` + `thread_id`** is the actual killer feature here: a user says "I sold pizza," the graph detects missing amount/quantity, asks a clarifying question, and the *next* HTTP request (a different process invocation) needs to resume the same conversation. LangGraph's checkpointer plus a `thread_id` (persisted as `num` in the `recommendations` Mongo doc) is what makes that possible across stateless HTTP calls — plain function chaining has no story for this at all.
- The `TransactionType` enum already includes `waste`, `unsold`, `correction` that aren't wired into the graph yet — the graph structure is built to be extended with new node types without touching existing ones (open/closed principle for agent pipelines).

**Tradeoff to admit:** LangGraph adds real complexity and a dependency surface (state schema management via `TypedDict` + `add_messages` reducer, checkpointer storage) for what is, at its core, a 4–5 step pipeline. For a smaller scope you could hand-roll this with plain async functions and an `if/elif` dispatcher and it would work — LangGraph earns its keep specifically because of the multi-turn resumability requirement, not because "agents need a framework."

---

## 3. Why two Whisper models (base *and* large-v3-turbo) instead of just one?

**Decision:** `speech_to_text_base` runs first and streams `fast_text` immediately; `speech_to_text_turbo` runs after and streams `accurate_text_ready`, which is what's actually used for extraction (base's output is discarded if turbo succeeds).

**Why:** This is a **latency-vs-accuracy UX tradeoff solved by racing both, not choosing one.**
- `base` is small and fast — gives the user near-instant feedback that their audio was understood (perceived latency matters a lot for a voice-first street-vendor UX; dead air after recording feels broken).
- `large-v3-turbo` is much more accurate, especially for code-switched Hindi/English speech, but slower — it runs in the background while the user is already looking at the fast (possibly slightly wrong) transcript, and the UI can swap it in when ready.
- Both use `task="translate"` to force English output regardless of input language — this normalizes downstream LLM extraction to one language even though vendors speak Hindi/regional languages, while the *response* to the vendor is still generated in their `lang` (see `get_vendor_language`).

**Tradeoff to admit:** Running two models means 2x compute per audio clip and two model-loads in memory at startup (`model_base`, `model_turbo` both loaded globally) — expensive on CPU, and there's no fallback path if turbo fails other than silently using `fast_text` (`if not accurate_text: accurate_text = fast_text`). A cleaner production version would only run turbo and accept the latency, or make the base-pass optional per client capability.

---

## 4. Why SSE over WebSockets or plain polling?

**Decision:** Both `/api/speech_msg` and `/api/recommend_msg` return `StreamingResponse(..., media_type="text/event-stream")`.

**Why:**
- The communication is **strictly one-directional** — server pushes pipeline progress (transcribing → refining → agent processing → saved), client never needs to push data mid-stream. WebSockets solve a harder problem (full duplex) that isn't needed here, at the cost of connection management, ping/pong keepalive, and reconnect logic you'd have to write yourself.
- SSE runs over plain HTTP/1.1, so it survives typical corporate proxies/firewalls that sometimes choke on WS upgrade handshakes, and the browser's native `EventSource` auto-reconnects on drop — free reliability WebSockets don't give you without extra code.
- Polling would mean the client repeatedly asking "done yet?" — wasteful for a multi-second pipeline (STT + two LLM passes can take real time) and it can't cheaply deliver *intermediate* stage updates without many round trips.

**Tradeoff to admit:** SSE is one-directional by design — if this pipeline needed the client to send corrections mid-stream (e.g., "no, cancel the transaction" while it's still transcribing), SSE can't do that on the same connection; you'd need a second channel or WS. Also each SSE call is a long-held HTTP connection, which doesn't scale on the default single Uvicorn worker without something like Gunicorn+Uvicorn workers or a proper ASGI server config under load.

---

## 5. Why MongoDB over a relational DB here?

**Decision:** Mongo (via Motor async driver) stores `saleevents`, `dailyrecords`, `recommendations`, `vendors`, `insights`.

**Why:**
- **Schema polymorphism is real, not incidental.** `SaleTransaction` has `item/quantity/pricePerUnit`, `ExpenseTransaction` has `expenseType/note`, `UdharTransaction` has `personName` — three genuinely different shapes for "a transaction." In SQL that's either three tables with a shared parent (extra joins on every read) or one wide table full of nullable columns. Mongo just stores each document as its natural shape.
- `dailyrecords` embeds arrays directly (`itemsSold`, `unsoldItems`, `wastedItems`) — this is a natural document-DB pattern (embed one-to-few nested data) that would otherwise be 3 child tables + joins for what's really "one day's summary for one vendor."
- Motor's async driver is a natural fit with FastAPI's async handlers — no blocking DB calls stalling the event loop.
- Fast iteration mattered (hackathon-origin project) — adding a new transaction type or a new field to `vendors.items` doesn't require a migration.

**Where Mongo is the *right* call:** transactional/operational data with variable shape per record type, read/write patterns keyed by `vendorId + date` (exactly what `fetch_vendor_daily_records` does — `$gte` on date, sorted, limited), and data you mostly access by known keys rather than complex multi-table joins.

**Where Mongo is the *wrong* tool (and RAG/vector store would be better):** the `recommender` node currently stuffs the **entire item catalog as JSON text into the LLM prompt** (`item_catalog_str = json.dumps(item_catalog...)`) so the model can match a spoken item name against it. That works at 10–20 items. At real scale (hundreds of catalog items, fuzzy/misheard item names, multilingual synonyms), that's the textbook case for embeddings + vector similarity search (or Mongo Atlas Vector Search, or a dedicated vector DB) — embed each catalog item once, embed the spoken phrase, do a nearest-neighbor lookup, and only inject the top-k matches into the prompt instead of the whole catalog. This also caps token cost per request instead of growing linearly with catalog size. **This is a genuinely good "what would you change" answer for an interview** — you're not defending everything as perfect, you're showing you know where the current design has a scaling ceiling and what the fix looks like.

**Tradeoff to admit generally:** Mongo gives up strong relational integrity — nothing enforces that `vendorId` in `saleevents` actually references a real vendor at the DB level; that's application-level discipline only (`ObjectId(vendor_id)` conversions everywhere, no FK constraint). For financial-adjacent data (this *is* money in/out), that's a real risk a SQL-leaning interviewer will flag, and it's fair — the honest answer is "acceptable for a hackathon/MVP, I'd add schema validation rules or move ledger-critical writes to a system with stronger consistency guarantees before scaling."

---

## 6. Why structured output (Pydantic schemas) instead of parsing free-text LLM responses?

**Decision:** Every extraction node uses `llm.with_structured_output(SomeSchema)` — `Check`, `TransactionType`, `SaleTransaction`, `ExpenseTransaction`, `UdharTransaction`.

**Why:** Regex/free-text parsing of LLM output is fragile and silently wrong (model says "around 80rs" and your regex either crashes or extracts "80" and drops "around"). Structured output constrains the model to emit a schema-conformant object, so `amount: float` is guaranteed to be a float or the call fails loudly — you get validation for free instead of writing custom parsers per field, and it composes cleanly with FastAPI's own Pydantic validation on the way out.

**Tradeoff to admit:** Structured output still trusts the model's *judgment* about ambiguous cases (e.g., inferring `pricePerUnit` correctly) — schema conformance isn't the same as semantic correctness. The `confidence` field and `flags` list (`approximation_used`, `missing_quantity`, `ambiguous_item`) are the mitigation — pushing uncertainty into explicit fields the downstream logic (or a human) can act on, rather than pretending every extraction is ground truth.

---

## 7. Why validate-then-extract as two separate LLM calls instead of one "extract or ask" call?

**Decision:** `query_checker_*` (a strict yes/no completeness check) always runs before `query_maker_*` (extraction) — and extraction is *only* reached via the `correct` branch of `route_query`.

**Why:** This is a **fail-fast gate.** If extraction ran directly on an incomplete message, the model would be tempted to *invent* a plausible amount or quantity to satisfy the schema (structured output forces every required field to have a value) — that's a silent data-integrity bug for a financial system. Splitting "is this complete?" into its own strict, low-temperature call with explicit few-shot examples (see the `query_checker_sale` prompt) means missing data gets caught and routed to clarification *before* anything hallucinated reaches the database.

**Tradeoff to admit:** Two sequential LLM calls instead of one means roughly 2x latency and cost for every valid transaction (the common case), to protect against the invalid case. Reasonable given this is financial logging, but worth naming as a deliberate cost/safety tradeoff, not a free lunch.

---

## 8. Why `gpt-4.1-mini` at `temperature=0` (with Groq/Llama commented out as an alternative)?

**Why:**
- `temperature=0` for structured extraction tasks — you want deterministic, repeatable parsing of "I sold 2 pizzas for 80 rupees," not creative variation.
- `mini` over full-size GPT-4.1 — these are short, well-scoped classification/extraction tasks (not open-ended reasoning), so a smaller model is cheap and fast without meaningfully hurting accuracy, and this pipeline runs per-voice-message, i.e. potentially very high volume.
- The commented-out `ChatGroq` (Llama 3.1 8B) shows the LLM is swappable via LangChain's model abstraction — a real production lever: Groq's inference is dramatically faster (LPU hardware) and cheaper, useful if latency on the SSE stream becomes the bottleneck, at some accuracy cost for a smaller open model.

---

## 9. Why offload daily-aggregate updates to a separate Node API call (`httpx.AsyncClient` → `NODE_API_URL`) instead of doing it in Python?

**Why:** Keeps this FastAPI service focused on *extraction/agent orchestration* and delegates *aggregation/business-rollup logic* to what's presumably the main product backend (Node/Express) that already owns that domain and probably has the rest of the vendor-facing CRUD. Avoids duplicating "how do we compute a vendor's daily summary" in two languages/codebases — single source of truth for that logic.

**Tradeoff to admit:** It's a fire-and-forget-ish `await client.post(...)` with no retry/backoff and no check on the response — if that Node endpoint is down, the sale still saves in Mongo but the daily aggregate silently doesn't update, and there's no queue/outbox pattern to guarantee eventual consistency. Fine for hackathon scope; the honest answer for "how would you productionize this" is a message queue (or at minimum a retry + dead-letter log) between the two services instead of a direct synchronous-ish HTTP call embedded in the save path.

---

## Quick-fire summary table (for rapid recall in interview)

| Decision | Core reason | Real tradeoff |
|---|---|---|
| FastAPI | Native async I/O, SSE, shared Pydantic schemas | No batteries-included admin/ORM (not needed here) |
| LangGraph | Explicit branching FSM + cross-request conversation memory via checkpointer/thread_id | Framework overhead for what's a ~5-node graph |
| Whisper base + turbo | Perceived-latency vs accuracy, raced not chosen | 2x compute, weak fallback on turbo failure |
| SSE | One-directional progress stream, HTTP-friendly, auto-reconnect | Can't take mid-stream client input; long-held connections |
| MongoDB | Polymorphic transaction shapes, embedded arrays, async driver fit | No FK integrity for financial data |
| Catalog matching (current: prompt-stuffing) | Simple, works at small scale | Doesn't scale — real fix is embeddings/vector search |
| Structured output (Pydantic) | Schema-guaranteed extraction | Doesn't guarantee semantic correctness — hence `confidence`/`flags` |
| Validate-then-extract | Prevents hallucinated required fields on incomplete input | 2x LLM calls per message |
| gpt-4.1-mini, temp=0 | Cheap, deterministic, right-sized for extraction | Swappable to Groq/Llama for latency at accuracy cost |
| Node API call for aggregates | Single source of truth for rollup logic | No retry/outbox — silent inconsistency risk |