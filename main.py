from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from typing import List, Optional
from io import BytesIO
import os
import logging
import mimetypes
from functools import partial
from concurrent.futures import ThreadPoolExecutor
import asyncio

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
api_id = 28437242
api_hash = "25ff44a57d1be2775b5fb60278ef724b"
string_session = os.environ.get("STRING_SESSION")
CHANNEL = "https://t.me/+yGEhMlthGkIxM2Rl"

# Thread pool for CPU-bound tasks
executor = ThreadPoolExecutor(max_workers=4)

# Initialize Telegram client
client = TelegramClient(StringSession(string_session), api_id, api_hash)
channel_entity = None

# FastAPI app
app = FastAPI(
    title="Telegram Media API",
    description="Efficient media streaming via Telegram",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Extended MIME types
mimetypes.add_type('video/webm', '.webm')
mimetypes.add_type('video/quicktime', '.mov')

@app.on_event("startup")
async def startup():
    global channel_entity
    try:
        await client.start()
        channel_entity = await client.get_entity(CHANNEL)
        logger.info("Telegram client started")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()
    logger.info("Telegram client disconnected")

@app.post("/upload")
async def upload(file: UploadFile):
    try:
        data = await file.read()
        msg = await client.send_file(
            channel_entity,
            BytesIO(data),
            file_name=file.filename,
            caption=file.filename,
            part_size_kb=512,
            workers=4
        )
        return {"id": msg.id, "name": file.filename}
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(500, "Upload failed")

@app.get("/files")
async def list_files():
    try:
        messages = await client.get_messages(channel_entity, limit=100)
        files = []
        
        for msg in messages:
            if not msg.media:
                continue
                
            file_info = {
                "id": msg.id,
                "name": msg.message or f"file_{msg.id}",
                "mime": "application/octet-stream",
                "size": 0
            }

            if hasattr(msg.media, "document"):
                doc = msg.media.document
                file_info["mime"] = doc.mime_type or file_info["mime"]
                file_info["size"] = doc.size
                if filename := next(
                    (a.file_name for a in doc.attributes 
                     if isinstance(a, DocumentAttributeFilename)), None
                ):
                    file_info["name"] = filename

            files.append(file_info)
            
        return JSONResponse(files)
    except Exception as e:
        logger.error(f"List failed: {e}")
        raise HTTPException(500, "List failed")

@app.get("/stream/{msg_id}")
async def stream_file(msg_id: int, request: Request):
    try:
        msg = await client.get_messages(channel_entity, ids=msg_id)
        if not msg or not msg.media:
            raise HTTPException(404, "File not found")

        # Get file info
        file_name = msg.message or f"file_{msg.id}"
        file_size = getattr(msg.media.document, "size", None) if hasattr(msg.media, "document") else None
        mime = (getattr(msg.media.document, "mime_type", None) if hasattr(msg.media, "document") else None
        mime = mime or mimetypes.guess_type(file_name)[0] or "application/octet-stream"

        # Range request handling
        range_header = request.headers.get("range")
        if range_header and file_size:
            start, end = range_header.replace("bytes=", "").split("-")
            start = int(start)
            end = int(end) if end else file_size - 1
            content_length = end - start + 1
            
            async def ranged_stream():
                async for chunk in client.iter_download(
                    msg.media,
                    offset=start,
                    limit=content_length,
                    file_size=file_size
                ):
                    yield chunk

            return StreamingResponse(
                ranged_stream(),
                status_code=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(content_length),
                    "Content-Type": mime,
                    "Accept-Ranges": "bytes"
                },
                media_type=mime
            )

        # Full file stream
        async def full_stream():
            async for chunk in client.iter_download(msg.media):
                yield chunk

        headers = {
            "Content-Type": mime,
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=86400"
        }
        if file_size:
            headers["Content-Length"] = str(file_size)

        return StreamingResponse(
            full_stream(),
            headers=headers,
            media_type=mime
        )

    except Exception as e:
        logger.error(f"Stream failed: {e}")
        raise HTTPException(500, "Stream failed")

@app.delete("/delete/{msg_id}")
async def delete_file(msg_id: int):
    try:
        await client.delete_messages(channel_entity, msg_id)
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(500, "Delete failed")