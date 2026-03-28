import json
import asyncio
import os
import uuid
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tools.save_transaction import save_transaction
from tools.sp_text import speech_to_text_base, speech_to_text_turbo
from tools.delete_recommendation import delete_recommendation
from agents.text_db_agent import main
import random


app = FastAPI(title="FinWell Agent API", version="1.0.0")

origins = ["http://localhost:3000","http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AgentQuery(BaseModel):
    userId: str
    query: str
    lang: str = "english"


@app.post("/api/speech_msg")
async def speech_input(
    meta: str = Form(...),
    audio: UploadFile = File(...),
    lang: str = Form(...)
):
    try:
        parsed = json.loads(meta)
        user_id = parsed["userId"]
        timestamp = str(parsed["timestamp"])
        print(f"Processing audio for User: {user_id}")

        audio_bytes = await audio.read()
        unique_file_id = str(uuid.uuid4())
        temp_path = f"temp_input_audio_{unique_file_id}.m4a"

        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        async def generate_response():
            try:
                # 1. Yield initial status
                yield f"data: {json.dumps({'status': 'Analyzing audio...'})}\n\n"

                # 2. Kick off both STT models simultaneously
                task_base = asyncio.create_task(
                    asyncio.to_thread(speech_to_text_base, temp_path, lang)
                )
                task_turbo = asyncio.create_task(
                    asyncio.to_thread(speech_to_text_turbo, temp_path, lang)
                )

                # 3. Yield fast result immediately
                fast_text = await task_base
                yield f"data: {json.dumps({'status': 'fast_text', 'text': fast_text})}\n\n"

                # 4. Wait for accurate result
                accurate_text = await task_turbo
                yield f"data: {json.dumps({'status': 'accurate_text_ready', 'text': accurate_text})}\n\n"

                # 5. ✅ async for — because main() is now an async generator
                async for step_update in main(accurate_text, vendor_id=user_id ,num=-1):
                    yield f"data: {json.dumps(step_update)}\n\n"

                    # Intercept the "complete" stage and save to DB
                    if step_update.get("stage") == "complete":
                        try:
                            inserted_id = await save_transaction(
                                agent_output=step_update,
                                vendor_id=user_id,
                                voice_url=None
                            )
                            yield f"data: {json.dumps({'stage': 'saved', 'id': inserted_id})}\n\n"

                        except Exception as db_err:
                            yield f"data: {json.dumps({'stage': 'db_error', 'error': str(db_err)})}\n\n"

            except Exception as stream_err:
                yield f"data: {json.dumps({'error': str(stream_err)})}\n\n"

            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        return StreamingResponse(generate_response(), media_type="text/event-stream")

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing speech input: {str(e)}"
        )

@app.post("/api/recommend_msg")
async def speech_input(
    meta: str = Form(...),
    lang: str = Form(...)
):
    try:
        parsed = json.loads(meta)
        num = parsed.get("num")
        vendor_id = parsed.get("userId")
        msg = parsed.get("msg")
        print(msg)
        if not vendor_id or not msg:
            raise HTTPException(status_code=400, detail="Missing userId or msg")

        print(f"Processing message for User: {vendor_id}")

        async def generate_response():
            try:
                yield f"data: {json.dumps({'status': 'Processing message...'})}\n\n"

                try:
                    deleted_count = await delete_recommendation(vendor_id)
                    yield f"data: {json.dumps({'stage': 'cleanup', 'deleted': deleted_count})}\n\n"
                except Exception as del_err:
                    yield f"data: {json.dumps({'stage': 'cleanup_error', 'error': str(del_err)})}\n\n"

                async for step_update in main(voice_text=msg, vendor_id=vendor_id,num=num):
                    yield f"data: {json.dumps(step_update)}\n\n"

                    if step_update.get("stage") == "complete":
                        try:
                            inserted_id = await save_transaction(
                                agent_output=step_update,
                                vendor_id=vendor_id,
                                voice_url=None
                            )
                            yield f"data: {json.dumps({'stage': 'saved', 'id': inserted_id})}\n\n"

                        except Exception as db_err:
                            yield f"data: {json.dumps({'stage': 'db_error', 'error': str(db_err)})}\n\n"

            except Exception as stream_err:
                yield f"data: {json.dumps({'error': str(stream_err)})}\n\n"

        return StreamingResponse(generate_response(), media_type="text/event-stream")

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )