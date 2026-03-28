import json
import asyncio
import os
import uuid  # Added to prevent file collisions
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tools.save_transaction import save_transaction

# 1️⃣ Import the two new separated functions
from tools.sp_text import speech_to_text_base, speech_to_text_turbo
from agents.text_db_agent import main

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
    lang: str = "hi"

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
        
        # Save uploaded audio with a UNIQUE name so concurrent users don't overwrite each other
        audio_bytes = await audio.read()
        unique_file_id = str(uuid.uuid4())
        temp_path = f"temp_input_audio_{unique_file_id}.m4a"
        
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        model_lang = "hi" if lang.lower() == "hindi" else "en"
            
        async def generate_response():
            try:
                # 1. Yield initial status
                yield f"data: {json.dumps({'status': 'Analyzing audio...'})}\n\n"
                
                # 2️⃣ KICK OFF BOTH MODELS SIMULTANEOUSLY
                # They will run in separate background threads without blocking FastAPI
                task_base = asyncio.create_task(
                    asyncio.to_thread(speech_to_text_base, temp_path, lang)
                )
                task_turbo = asyncio.create_task(
                    asyncio.to_thread(speech_to_text_turbo, temp_path, lang)
                )
                
                # 3️⃣ WAIT FOR THE FAST MODEL AND YIELD IMMEDIATELY
                fast_text = await task_base
                # We tag this as "fast_text" so the frontend knows it's the preliminary result
                yield f"data: {json.dumps({'status': 'fast_text', 'text': fast_text})}\n\n"

                yield f"data: {json.dumps({'status': 'Refining text for accuracy...'})}\n\n"
                
                # 4️⃣ WAIT FOR THE HEAVY MODEL
                # (Since we used create_task earlier, it has already been running this whole time)
                accurate_text = await task_turbo
                
                # Optional: Let the frontend know we are starting the LangGraph DB process
                yield f"data: {json.dumps({'status': 'accurate_text_ready', 'text': accurate_text})}\n\n"
                
                # 5️⃣ RUN YOUR LANGGRAPH GENERATOR
                # Pass the highly accurate text into your main agent
                for step_update in main(accurate_text):
                    yield f"data: {json.dumps(step_update)}\n\n"

                    # ✅ Intercept the "complete" stage and save to DB
                    if step_update.get("stage") == "complete":
                        try:
                            inserted_id = await save_transaction(
                                agent_output=step_update,
                                vendor_id=user_id,
                                voice_url=None   # pass a real URL if you upload audio to S3/GCS
                            )
                            yield f"data: {json.dumps({'stage': 'saved', 'id': inserted_id})}\n\n"
                        
                        except Exception as db_err:
                            yield f"data: {json.dumps({'stage': 'db_error', 'error': str(db_err)})}\n\n"
                    
            except Exception as stream_err:
                yield f"data: {json.dumps({'error': str(stream_err)})}\n\n"
            finally:
                # Always clean up the unique temporary audio file when done
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        # --- RETURN THE STREAM ---
        return StreamingResponse(generate_response(), media_type="text/event-stream")

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing speech input: {str(e)}"
        )
    
