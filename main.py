from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse as StarletteStreamingResponse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from typing import List
import os
import asyncio
from datetime import datetime
import aiofiles
import mimetypes
import logging

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Telegram credentials from environment variables
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
app = FastAPI()

# CORS settings (open to all origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await client.start()

@app.get("/", response_class=HTMLResponse)
async def index():
    return "<h1>Telegram File API</h1><p>Use /upload, /files, /delete, /stream</p>"

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        filename_attr = DocumentAttributeFilename(file.filename)
        await client.send_file("me", file=contents, attributes=[filename_attr])
        return {"status": "success", "filename": file.filename}
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/files")
async def list_files():
    try:
        messages = await client.get_messages("me", limit=100)
        files = []
        for msg in messages:
            if msg.file:
                files.append({
                    "id": msg.id,
                    "name": msg.file.name,
                    "mime": msg.file.mime_type,
                    "size": msg.file.size,
                    "date": msg.date.isoformat(),
                })
        return files
    except Exception as e:
        logger.error(f"List error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.delete("/delete/{file_id}")
async def delete_file(file_id: int):
    try:
        await client.delete_messages("me", message_ids=[file_id])
        return {"status": "deleted", "id": file_id}
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/stream/{file_id}")
async def stream_file(file_id: int, request: Request):
    try:
        msg = await client.get_messages("me", ids=file_id)
        if not msg or not msg.file:
            return JSONResponse(status_code=404, content={"error": "File not found"})

        filename = msg.file.name or f"video_{file_id}.mp4"
        file_path = f"temp_{file_id}_{filename}"
        await client.download_media(msg, file=file_path)

        file_size = os.path.getsize(file_path)
        content_type = msg.file.mime_type or mimetypes.guess_type(file_path)[0] or "application/octet-stream"

        range_header = request.headers.get("range")
        if range_header:
            start, end = range_header.replace("bytes=", "").split("-")
            start = int(start)
            end = int(end) if end else file_size - 1
        else:
            start, end = 0, file_size - 1

        chunk_size = end - start + 1

        async def file_chunker(path, start, end):
            async with aiofiles.open(path, "rb") as f:
                await f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    chunk = await f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
            os.remove(path)

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": content_type,
        }

        return StarletteStreamingResponse(file_chunker(file_path, start, end), status_code=206, headers=headers)

    except Exception as e:
        logger.error(f"Stream error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})