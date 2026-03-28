import json
import asyncio
import os
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tools.sp_text import speech_to_text
from agents.text_db_agent import main

# Note: You'll need to import your custom speech_to_text function
# from wherever you defined it in your project.
# from your_module import speech_to_text
app = FastAPI(title="FinWell Agent API", version="1.0.0")

origins = ["http://localhost:3000"]
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
        print(user_id)
        # Save uploaded audio
        audio_bytes = await audio.read()
        temp_path = "temp_input_audio.m4a"
        
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)
        async def generate_response():
            try:
                # 1. Yield initial status
                yield f"data: {json.dumps({'status': 'Analyzing audio...'})}\n\n"
                
                # 2. Run Whisper in a background thread so it doesn't freeze FastAPI
                sms_text = await asyncio.to_thread(speech_to_text, temp_path, lang)
                yield f"data: {json.dumps({'status': f'Text extracted: {sms_text}'})}\n\n"
                
                # 3. Loop through the LangGraph generator and yield its steps
                for step_update in main(sms_text):
                    yield f"data: {json.dumps(step_update)}\n\n"
                    
            except Exception as stream_err:
                yield f"data: {json.dumps({'error': str(stream_err)})}\n\n"
            finally:
                # Always clean up the temporary audio file when done
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        # --- RETURN THE STREAM ---
        return StreamingResponse(generate_response(), media_type="text/event-stream")
        



    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing speech input: {str(e)}"
        )

