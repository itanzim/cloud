from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from typing import List
from io import BytesIO
from PIL import Image
import os

# 🔐 Telegram credentials
api_id = 28437242
api_hash = "25ff44a57d1be2775b5fb60278ef724b"
string = os.environ.get("STRING_SESSION")  # Set this in Render env vars

# 📦 Telegram client & channel entity
client = TelegramClient(StringSession(string), api_id, api_hash)
channel_entity = None

app = FastAPI()

# 🌍 CORS for cross-origin frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚀 On startup: connect client & resolve private channel
@app.on_event("startup")
async def startup_event():
    global channel_entity
    await client.start()
    channel_entity = await client.get_entity("https://t.me/+yGEhMlthGkIxM2Rl")
    print("✅ Telegram client started and channel resolved")

# 📴 On shutdown: disconnect client
@app.on_event("shutdown")
async def shutdown_event():
    await client.disconnect()
    print("🔌 Telegram client disconnected")

# 📤 Upload a single file
@app.post("/upload")
async def upload(file: UploadFile):
    data = await file.read()
    name = file.filename
    bio = BytesIO(data)
    bio.name = name

    thumb_id = None
    if file.content_type.startswith("image/"):
        try:
            image = Image.open(BytesIO(data))
            image.thumbnail((300, 300))
            thumb_io = BytesIO()
            thumb_io.name = f"thumb_{name}"
            image.save(thumb_io, format=image.format or 'JPEG')
            thumb_io.seek(0)
            msg_thumb = await client.send_file(channel_entity, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}")
            thumb_id = msg_thumb.id
        except Exception as e:
            print("⚠️ Thumbnail generation failed:", e)

    msg = await client.send_file(channel_entity, bio, file_name=name, caption=name)
    return {"status": "uploaded", "id": msg.id, "thumbnail_id": thumb_id}

# 📤 Upload multiple files
@app.post("/upload-multiple")
async def upload_multiple(files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        data = await file.read()
        name = file.filename
        bio = BytesIO(data)
        bio.name = name
        thumb_id = None

        if file.content_type.startswith("image/"):
            try:
                image = Image.open(BytesIO(data))
                image.thumbnail((300, 300))
                thumb_io = BytesIO()
                thumb_io.name = f"thumb_{name}"
                image.save(thumb_io, format=image.format or 'JPEG')
                thumb_io.seek(0)
                msg_thumb = await client.send_file(channel_entity, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}")
                thumb_id = msg_thumb.id
            except Exception as e:
                print(f"⚠️ Thumbnail generation failed for {name}:", e)

        msg = await client.send_file(channel_entity, bio, file_name=name, caption=name)
        results.append({"id": msg.id, "thumbnail_id": thumb_id, "name": name})

    return {"status": "uploaded", "files": results}

# 📥 List uploaded files
@app.get("/files")
async def list_files():
    messages = await client.get_messages(channel_entity, limit=100)
    files = []
    thumb_map = {}

    for msg in messages:
        if msg.media and hasattr(msg.media, 'document') and msg.message and msg.message.startswith("thumb:"):
            original_name = msg.message.replace("thumb:", "")
            thumb_map[original_name] = msg.id

    for msg in messages:
        if msg.media and hasattr(msg.media, 'document') and (not msg.message or not msg.message.startswith("thumb:")):
            doc = msg.media.document
            attrs = doc.attributes
            filename = next((a.file_name for a in attrs if isinstance(a, DocumentAttributeFilename)), None)
            if not filename:
                filename = msg.message or "unnamed"

            files.append({
                "id": msg.id,
                "name": filename,
                "mime": doc.mime_type,
                "size": doc.size,
                "thumbnail_id": thumb_map.get(filename)
            })

    return JSONResponse(content=files)

# ❌ Delete one file
@app.delete("/delete/{msg_id}")
async def delete_file(msg_id: int):
    try:
        await client.delete_messages(channel_entity, msg_id)
        return {"status": "deleted"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ❌ Delete multiple files
@app.post("/delete-multiple")
async def delete_multiple(ids: List[int]):
    try:
        await client.delete_messages(channel_entity, ids)
        return {"status": "deleted", "count": len(ids)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 📥 Stream a file
@app.get("/stream/{msg_id}")
async def stream_file(msg_id: int):
    msg = await client.get_messages(channel_entity, ids=msg_id)
    if not msg or not msg.media or not hasattr(msg.media, "document"):
        return JSONResponse(status_code=404, content={"error": "File not found"})

    doc = msg.media.document
    file = await client.download_media(doc, file=BytesIO())
    file.seek(0)
    return StreamingResponse(file, media_type=doc.mime_type)