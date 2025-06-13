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
import imageio.v3 as iio
import numpy as np

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram API credentials
api_id = 28437242
api_hash = "25ff44a57d1be2775b5fb60278ef724b"
string_session = os.environ.get("STRING_SESSION")

client = TelegramClient(StringSession(string_session), api_id, api_hash)
channel_entity = None

app = FastAPI(
    title="Telegram Media API",
    description="Upload, list, stream, and delete media via Telegram",
    version="1.0.0",
)

# CORS middleware
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
                msg_thumb = await client.send_file(
                    channel_entity, thumb_io,
                    file_name=thumb_io.name,
                    caption=f"thumb:{name}"
                )
                thumb_id = msg_thumb.id
            except Exception as e:
                logger.warning(f"Image thumbnail failed for {name}: {e}")

        # Video thumbnail
        elif file.content_type.startswith("video/"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_input:
                    temp_input.write(data)
                    temp_input.flush()

                    frame = iio.imread(temp_input.name, index=0, plugin="pyav")
                    image = Image.fromarray(np.array(frame))
                    image.thumbnail((300, 300))

                    thumb_io = BytesIO()
                    thumb_io.name = f"thumb_{name}.jpg"
                    image.save(thumb_io, format="JPEG")
                    thumb_io.seek(0)

                    msg_thumb = await client.send_file(
                        channel_entity, thumb_io,
                        file_name=thumb_io.name,
                        caption=f"thumb:{name}"
                    )
                    thumb_id = msg_thumb.id
            except Exception as e:
                logger.warning(f"Video thumbnail failed for {name}: {e}")

        # Send main file
        msg = await client.send_file(
            channel_entity, bio,
            file_name=name,
            caption=name
        )
        return {"status": "uploaded", "id": msg.id, "thumbnail_id": thumb_id}
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")

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
                        channel_entity, thumb_io,
                        file_name=thumb_io.name,
                        caption=f"thumb:{name}"
                    )
                    thumb_id = msg_thumb.id
                except Exception as e:
                    logger.warning(f"Image thumbnail failed for {name}: {e}")

            elif file.content_type.startswith("video/"):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_input:
                        temp_input.write(data)
                        temp_input.flush()

                        frame = iio.imread(temp_input.name, index=0, plugin="pyav")
                        image = Image.fromarray(np.array(frame))
                        image.thumbnail((300, 300))

                        thumb_io = BytesIO()
                        thumb_io.name = f"thumb_{name}.jpg"
                        image.save(thumb_io, format="JPEG")
                        thumb_io.seek(0)

                        msg_thumb = await client.send_file(
                            channel_entity, thumb_io,
                            file_name=thumb_io.name,
                            caption=f"thumb:{name}"
                        )
                        thumb_id = msg_thumb.id
                except Exception as e:
                    logger.warning(f"Video thumbnail failed for {name}: {e}")

            msg = await client.send_file(
                channel_entity, bio,
                file_name=name,
                caption=name
            )
            results.append({"id": msg.id, "thumbnail_id": thumb_id, "name": name})

        return {"status": "uploaded", "files": results}
    except Exception as e:
        logger.error(f"Multiple upload failed: {e}")
        raise HTTPException(status_code=500, detail="Multiple upload failed")

@app.get("/files")
async def list_files():
    try:
        messages = await client.get_messages(channel_entity, limit=100)
        files = []
        thumb_map = {}

        # Map thumbnails
        for msg in messages:
            if msg.media and hasattr(msg.media, "document") and msg.message and msg.message.startswith("thumb:"):
                orig = msg.message.replace("thumb:", "")
                thumb_map[orig] = msg.id

        # List media
        for msg in messages:
            if msg.media:
                mime = None
                size = None
                file_type = "unknown"
                filename = msg.message or f"file_{msg.id}"

                if hasattr(msg.media, "document") and msg.media.document:
                    doc = msg.media.document
                    mime = doc.mime_type
                    size = doc.size
                    filename = next(
                        (a.file_name for a in doc.attributes if isinstance(a, DocumentAttributeFilename)),
                        filename
                    )
                    file_type = "video" if mime and mime.startswith("video/") else "document"

                elif hasattr(msg.media, "photo") and msg.media.photo:
                    mime = "image/jpeg"
                    file_type = "photo"

                elif hasattr(msg.media, "video") and msg.media.video:
                    mime = "video/mp4"
                    file_type = "video"

                if file_type != "unknown":
                    files.append({
                        "id": msg.id,
                        "name": filename,
                        "type": file_type,
                        "mime": mime,
                        "size": size,
                        "thumbnail_id": thumb_map.get(filename)
                    })

        return JSONResponse(content=files)
    except Exception as e:
        logger.error(f"List files failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to list media")

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

        data_stream = await client.download_media(media, file=BytesIO())
        data_stream.seek(0)
        file_size = len(data_stream.getvalue())

        range_header = request.headers.get("range")
        if range_header:
            start, end = range_header.replace("bytes=", "").split("-")
            start = int(start)
            end = int(end) if end else file_size - 1
            chunk = end - start + 1
            data_stream.seek(start)
            chunk_data = data_stream.read(chunk)
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk),
                "Content-Type": mime,
            }
            return Response(content=chunk_data, status_code=206, headers=headers)
        return StreamingResponse(data_stream, media_type=mime)
    except Exception as e:
        logger.error(f"Stream failed: {e}")
        raise HTTPException(status_code=500, detail="Stream failed")

@app.delete("/delete/{msg_id}")
async def delete_file(msg_id: int):
    try:
        await client.delete_messages(channel_entity, msg_id, revoke=True)
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail="Delete failed")

@app.post("/delete-multiple")
async def delete_multiple(ids: List[int]):
    try:
        await client.delete_messages(channel_entity, ids, revoke=True)
        return {"status": "deleted", "count": len(ids)}
    except Exception as e:
        logger.error(f"Delete multiple failed: {e}")
        raise HTTPException(status_code=500, detail="Delete multiple failed")

This covers **all endpoints** with image and video thumbnail generation using `imageio`. You can copy-paste this into your `main.py`. Let me know if you need further tweaks!