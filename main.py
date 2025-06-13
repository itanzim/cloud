from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import FloodWaitError, FileReferenceExpiredError
from typing import List
from io import BytesIO
from PIL import Image
from starlette.responses import Response
import tempfile
import os
import logging

# Video thumbnail dependency
from moviepy.editor import VideoFileClip

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram credentials
api_id = 28437242
api_hash = "25ff44a57d1be2775b5fb60278ef724b"
string_session = os.environ.get("STRING_SESSION")

client = TelegramClient(StringSession(string_session), api_id, api_hash)
channel_entity = None

# FastAPI app
app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.on_event("shutdown")
async def shutdown_event():
    try:
        await client.disconnect()
        logger.info("🔌 Telegram client disconnected")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

@app.post("/upload")
async def upload(file: UploadFile):
    try:
        data = await file.read()
        name = file.filename
        bio = BytesIO(data)
        bio.name = name
        thumb_id = None

        # Image thumbnail
        if file.content_type.startswith("image/"):
            try:
                image = Image.open(BytesIO(data))
                image.thumbnail((300, 300))
                thumb_io = BytesIO()
                thumb_io.name = f"thumb_{name}"
                image.save(thumb_io, format=image.format or "JPEG")
                thumb_io.seek(0)
                msg_thumb = await client.send_file(channel_entity, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}")
                thumb_id = msg_thumb.id
            except Exception as e:
                logger.warning(f"Image thumbnail failed for {name}: {e}")

        # Video thumbnail
        elif file.content_type.startswith("video/"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_input:
                    temp_input.write(data)
                    temp_input.flush()
                    clip = VideoFileClip(temp_input.name)
                    frame = clip.get_frame(0.5)
                    image = Image.fromarray(frame)
                    image.thumbnail((300, 300))
                    thumb_io = BytesIO()
                    thumb_io.name = f"thumb_{name}.jpg"
                    image.save(thumb_io, format="JPEG")
                    thumb_io.seek(0)
                    msg_thumb = await client.send_file(channel_entity, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}")
                    thumb_id = msg_thumb.id
            except Exception as e:
                logger.warning(f"Video thumbnail failed for {name}: {e}")

        msg = await client.send_file(channel_entity, bio, file_name=name, caption=name)
        return {"status": "uploaded", "id": msg.id, "thumbnail_id": thumb_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

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

            # Image thumbnail
            if file.content_type.startswith("image/"):
                try:
                    image = Image.open(BytesIO(data))
                    image.thumbnail((300, 300))
                    thumb_io = BytesIO()
                    thumb_io.name = f"thumb_{name}"
                    image.save(thumb_io, format=image.format or "JPEG")
                    thumb_io.seek(0)
                    msg_thumb = await client.send_file(channel_entity, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}")
                    thumb_id = msg_thumb.id
                except Exception as e:
                    logger.warning(f"Image thumbnail failed for {name}: {e}")

            # Video thumbnail
            elif file.content_type.startswith("video/"):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_input:
                        temp_input.write(data)
                        temp_input.flush()
                        clip = VideoFileClip(temp_input.name)
                        frame = clip.get_frame(0.5)
                        image = Image.fromarray(frame)
                        image.thumbnail((300, 300))
                        thumb_io = BytesIO()
                        thumb_io.name = f"thumb_{name}.jpg"
                        image.save(thumb_io, format="JPEG")
                        thumb_io.seek(0)
                        msg_thumb = await client.send_file(channel_entity, thumb_io, file_name=thumb_io.name, caption=f"thumb:{name}")
                        thumb_id = msg_thumb.id
                except Exception as e:
                    logger.warning(f"Video thumbnail failed for {name}: {e}")

            msg = await client.send_file(channel_entity, bio, file_name=name, caption=name)
            results.append({"id": msg.id, "thumbnail_id": thumb_id, "name": name})

        return {"status": "uploaded", "files": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Multiple upload failed: {e}")

@app.get("/files")
async def list_files():
    try:
        messages = await client.get_messages(channel_entity, limit=100)
        files = []
        thumb_map = {}

        for msg in messages:
            if msg.media and hasattr(msg.media, "document") and msg.message and msg.message.startswith("thumb:"):
                original_name = msg.message.replace("thumb:", "")
                thumb_map[original_name] = msg.id

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list media: {e}")

@app.get("/stream/{msg_id}")
async def stream_file(msg_id: int, request: Request):
    try:
        msg = await client.get_messages(channel_entity, ids=msg_id)
        if not msg or not msg.media:
            raise HTTPException(status_code=404, detail="File not found")

        media = msg.media
        mime = "application/octet-stream"

        if hasattr(media, "document") and media.document:
            mime = media.document.mime_type or mime
        elif hasattr(media, "photo") and media.photo:
            mime = "image/jpeg"
        elif hasattr(media, "video") and media.video:
            mime = "video/mp4"

        full_file = await client.download_media(media, file=BytesIO())
        full_file.seek(0)
        file_size = len(full_file.getvalue())

        range_header = request.headers.get("range")
        if range_header:
            range_value = range_header.replace("bytes=", "")
            start_str, end_str = range_value.split("-")
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
            chunk_size = end - start + 1
            full_file.seek(start)
            data = full_file.read(chunk_size)
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": mime,
            }
            return Response(content=data, status_code=206, headers=headers)
        else:
            return StreamingResponse(full_file, media_type=mime)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stream failed: {e}")

@app.delete("/delete/{msg_id}")
async def delete_file(msg_id: int):
    try:
        await client.delete_messages(channel_entity, msg_id)
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

@app.post("/delete-multiple")
async def delete_multiple(ids: List[int]):
    try:
        await client.delete_messages(channel_entity, ids)
        return {"status": "deleted", "count": len(ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete multiple failed: {e}")