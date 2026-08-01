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