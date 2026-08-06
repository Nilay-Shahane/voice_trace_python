3. Add better tracing metadata

Your current:

config = {'configurable': {'thread_id': num}}

is good for LangGraph memory.

I would change it to:

config = {
    "configurable": {
        "thread_id": str(num)
    },
    "metadata": {
        "vendor_id": vendor_id,
        "conversation_id": num,
        "application": "transaction-agent"
    },
    "tags": [
        "production",
        "transaction-classifier"
    ]
}

Now in LangSmith you can filter:

vendor_id=test_vendor
application=transaction-agent




2. Why Concurrent Whisper Execution Is Better

Previously, the Base and Turbo Whisper models ran sequentially:

Base Model → Wait → Fast Text → Turbo Model → Wait → Accurate Text

This means Turbo starts only after Base finishes, increasing total processing time.

Example:

Base:   █████ (2 sec)

Turbo:        ███████████ (5 sec)

Total = 7 sec

With the new approach:

task_base = asyncio.create_task(asyncio.to_thread(speech_to_text_base, temp_path, lang))
task_turbo = asyncio.create_task(asyncio.to_thread(speech_to_text_turbo, temp_path, lang))

both models start immediately:

Base:   █████ (2 sec)

Turbo:  ███████████ (5 sec)

Now:

Base result is sent as soon as it finishes.
Turbo continues running in the background.
Final accurate text arrives faster.

Total processing time becomes:

max(Base time, Turbo time)

instead of:

Base time + Turbo time

This improves latency and user experience while keeping FastAPI responsive because Whisper inference runs in separate worker threads instead of blocking the async event loop.

Note: If both models run on the same GPU, parallel execution may not always be faster due to competition for GPU resources, so benchmarking is recommended.



1. Stream upload instead of loading entire audio into RAM (highest priority)

Change this:

audio_bytes = await audio.read()

with open(temp_path, "wb") as f:
    f.write(audio_bytes)

to:

with open(temp_path, "wb") as f:
    while chunk := await audio.read(1024 * 1024):  # 1MB chunks
        f.write(chunk)
Why?

Before:

20MB audio
    |
    v
RAM
    |
    v
Disk

After:

1MB chunk
    |
    v
Disk

You can say:

"I implemented streaming upload to avoid loading large audio files completely into memory."