from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from typing import List
import os
from io import BytesIO
from PIL import Image

# Telegram credentials
api_id = 28437242
api_hash = "25ff44a57d1be2775b5fb60278ef724b"
string = os.environ.get("STRING_SESSION")  # should be set in Render env
channel_id = -1002837205535

client = TelegramClient(StringSession(string), api_id, api_hash)
app = FastAPI()

# ✅ CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Use specific domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await client.start()
    print("✅ Telegram client started")

@app.on_event("shutdown")
async def shutdown_event():
    await client.disconnect()
    print("🔌 Telegram client disconnected")

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
            msg_thumb = await client.send_file(channel_id, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}")
            thumb_id = msg_thumb.id
        except Exception as e:
            print("⚠️ Thumbnail generation failed:", e)

    msg = await client.send_file(channel_id, bio, file_name=name, caption=name)
    return {"status": "uploaded", "id": msg.id, "thumbnail_id": thumb_id}

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
                msg_thumb = await client.send_file(channel_id, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}")
                thumb_id = msg_thumb.id
            except Exception as e:
                print(f"⚠️ Thumbnail generation failed for {name}:", e)

        msg = await client.send_file(channel_id, bio, file_name=name, caption=name)
        results.append({"id": msg.id, "thumbnail_id": thumb_id, "name": name})

    return {"status": "uploaded", "files": results}

@app.get("/files")
async def list_files():
    try:
        await client.connect()  # ✅ always connect safely
    except Exception as e:
        print("⚠️ Connect failed:", e)

    messages = await client.get_messages(channel_id, limit=100)
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

@app.delete("/delete/{msg_id}")
async def delete_file(msg_id: int):
    try:
        await client.delete_messages(channel_id, msg_id)
        return {"status": "deleted"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/delete-multiple")
async def delete_multiple(ids: List[int]):
    try:
        await client.delete_messages(channel_id, ids)
        return {"status": "deleted", "count": len(ids)}
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