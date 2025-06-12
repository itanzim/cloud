from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
import os
from io import BytesIO

api_id = 28437242
api_hash = "25ff44a57d1be2775b5fb60278ef724b"
string = os.environ.get("STRING_SESSION")
channel_id = -1002837205535  # Use minus for channel id

client = TelegramClient(StringSession(string), api_id, api_hash)
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await client.start()
    print("Telegram client started")

@app.on_event("shutdown")
async def shutdown_event():
    await client.disconnect()

@app.post("/upload")
async def upload(file: UploadFile):
    data = await file.read()
    name = file.filename
    bio = BytesIO(data)
    bio.name = name  # Important: Set name so Telegram client sends correct filename
    await client.send_file(channel_id, bio, file_name=name, caption=name)
    return {"status": "uploaded", "filename": name}

@app.get("/files")
async def list_files():
    messages = await client.get_messages(channel_id, limit=50)
    files = []

    for msg in messages:
        if msg.media and hasattr(msg.media, 'document'):
            doc = msg.media.document
            attrs = doc.attributes
            filename = next((a.file_name for a in attrs if isinstance(a, DocumentAttributeFilename)), None)
            if not filename:
                filename = msg.message or "unnamed"

            files.append({
                "id": msg.id,
                "name": filename,
                "mime": doc.mime_type,
                "size": doc.size
            })

    return JSONResponse(content=files)