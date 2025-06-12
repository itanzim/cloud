from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
import os
from io import BytesIO

# Telegram credentials
api_id = 28437242
api_hash = "25ff44a57d1be2775b5fb60278ef724b"
string = os.environ.get("STRING_SESSION")  # Set this in your Render environment
channel_id = -1002837205535  # Replace with your own channel ID

# Init
client = TelegramClient(StringSession(string), api_id, api_hash)
app = FastAPI()

# Static UI
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

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
    bio.name = name  # Required for Telegram to preserve filename
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

@app.delete("/delete/{msg_id}")
async def delete_file(msg_id: int):
    try:
        await client.delete_messages(channel_id, msg_id)
        return {"status": "deleted"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/stream/{msg_id}")
async def stream_file(msg_id: int):
    msg = await client.get_messages(channel_id, ids=msg_id)
    if not msg or not msg.media or not hasattr(msg.media, "document"):
        return JSONResponse(status_code=404, content={"error": "File not found"})

    doc = msg.media.document
    file = await client.download_media(doc, file=BytesIO())
    file.seek(0)
    return StreamingResponse(file, media_type=doc.mime_type)