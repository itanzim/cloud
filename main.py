from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import FloodWaitError, FileReferenceExpiredError
from typing import List
from io import BytesIO
from PIL import Image
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram API credentials
api_id = 28437242
api_hash = "25ff44a57d1be2775b5fb60278ef724b"
string_session = os.environ.get("STRING_SESSION")

# Init Telegram client
client = TelegramClient(StringSession(string_session), api_id, api_hash)
channel_entity = None

# Init FastAPI
app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start Telegram client and resolve channel
@app.on_event("startup")
async def startup_event():
    global channel_entity
    try:
        await client.start()
        channel_entity = await client.get_entity("https://t.me/+yGEhMlthGkIxM2Rl")
        logger.info("✅ Telegram client started and channel resolved")
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start Telegram client: {e}")

# Disconnect Telegram client on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    try:
        await client.disconnect()
        logger.info("🔌 Telegram client disconnected")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

# Upload one file
@app.post("/upload")
async def upload(file: UploadFile):
    try:
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
                image.save(thumb_io, format=image.format or "JPEG")
                thumb_io.seek(0)
                msg_thumb = await client.send_file(
                    channel_entity, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}"
                )
                thumb_id = msg_thumb.id
                logger.info(f"Uploaded thumbnail: ID={msg_thumb.id}, Name={thumb_io.name}")
            except Exception as e:
                logger.warning(f"Thumbnail generation failed for {name}: {e}")

        msg = await client.send_file(channel_entity, bio, file_name=name, caption=name)
        logger.info(f"Uploaded file: ID={msg.id}, Name={name}")
        return {"status": "uploaded", "id": msg.id, "thumbnail_id": thumb_id}
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

# Upload multiple files
@app.post("/upload-multiple")
async def upload_multiple(files: List[UploadFile] = File(...)):
    try:
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
                    image.save(thumb_io, format=image.format or "JPEG")
                    thumb_io.seek(0)
                    msg_thumb = await client.send_file(
                        channel_entity, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}"
                    )
                    thumb_id = msg_thumb.id
                    logger.info(f"Uploaded thumbnail: ID={msg_thumb.id}, Name={thumb_io.name}")
                except Exception as e:
                    logger.warning(f"Thumbnail generation failed for {name}: {e}")

            msg = await client.send_file(channel_entity, bio, file_name=name, caption=name)
            logger.info(f"Uploaded file: ID={msg.id}, Name={name}")
            results.append({"id": msg.id, "thumbnail_id": thumb_id, "name": name})

        return {"status": "uploaded", "files": results}
    except Exception as e:
        logger.error(f"Multiple upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Multiple upload failed: {e}")

# List files (photos, videos, documents)
@app.get("/files")
async def list_files():
    try:
        messages = await client.get_messages(channel_entity, limit=100)
        logger.info(f"Fetched {len(messages)} messages")
        files = []
        thumb_map = {}

        # Map thumbnails
        for msg in messages:
            if msg.media and hasattr(msg.media, "document") and msg.message and msg.message.startswith("thumb:"):
                original_name = msg.message.replace("thumb:", "")
                thumb_map[original_name] = msg.id

        # Map files
        for msg in messages:
            if msg.media:
                file_type = "unknown"
                filename = msg.message or f"file_{msg.id}"
                mime = None
                size = None

                if hasattr(msg.media, "document") and msg.media.document:
                    doc = msg.media.document
                    mime = doc.mime_type
                    size = doc.size
                    filename = next(
                        (a.file_name for a in doc.attributes if isinstance(a, DocumentAttributeFilename)),
                        msg.message or f"document_{msg.id}"
                    )
                    file_type = "video" if mime and mime.startswith("video/") else "document"

                elif hasattr(msg.media, "photo") and msg.media.photo:
                    file_type = "photo"
                    filename = msg.message or f"photo_{msg.id}.jpg"
                    mime = "image/jpeg"

                elif hasattr(msg.media, "video") and msg.media.video:
                    file_type = "video"
                    filename = msg.message or f"video_{msg.id}.mp4"
                    mime = "video/mp4"

                else:
                    continue

                files.append({
                    "id": msg.id,
                    "name": filename,
                    "type": file_type,
                    "mime": mime,
                    "size": size,
                    "thumbnail_id": thumb_map.get(filename),
                })

        return JSONResponse(content=files)
    except FloodWaitError as e:
        logger.error(f"Rate limit hit: wait {e.seconds} seconds")
        raise HTTPException(status_code=429, detail=f"Rate limit hit, wait {e.seconds} seconds")
    except Exception as e:
        logger.error(f"List files error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list media: {e}")

# Delete one file
@app.delete("/delete/{msg_id}")
async def delete_file(msg_id: int):
    try:
        await client.delete_messages(channel_entity, msg_id)
        logger.info(f"Deleted file: ID={msg_id}")
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Delete error for ID={msg_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

# Delete multiple files
@app.post("/delete-multiple")
async def delete_multiple(ids: List[int]):
    try:
        await client.delete_messages(channel_entity, ids)
        logger.info(f"Deleted {len(ids)} files")
        return {"status": "deleted", "count": len(ids)}
    except Exception as e:
        logger.error(f"Delete multiple error: {e}")
        raise HTTPException(status_code=500, detail=f"Delete multiple failed: {e}")

# Stream files (photo, video, document)
@app.get("/stream/{msg_id}")
async def stream_file(msg_id: int):
    try:
        msg = await client.get_messages(channel_entity, ids=msg_id)
        if not msg or not msg.media:
            logger.error(f"No media found for msg_id: {msg_id}")
            raise HTTPException(status_code=404, detail="File not found")

        media = msg.media
        mime = "application/octet-stream"

        if hasattr(media, "document") and media.document:
            mime = media.document.mime_type or mime
        elif hasattr(media, "photo") and media.photo:
            mime = "image/jpeg"
        elif hasattr(media, "video") and media.video:
            mime = "video/mp4"

        file = await client.download_media(media, file=BytesIO())
        file.seek(0)

        logger.info(f"Streaming msg_id={msg_id} as {mime}")
        return StreamingResponse(file, media_type=mime)

    except FloodWaitError as e:
        logger.error(f"Flood wait: wait {e.seconds}s")
        raise HTTPException(status_code=429, detail=f"Rate limit, wait {e.seconds}s")
    except FileReferenceExpiredError:
        logger.error(f"File reference expired for {msg_id}")
        raise HTTPException(status_code=410, detail="File reference expired")
    except Exception as e:
        logger.error(f"Stream error for msg_id {msg_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Stream failed: {e}")