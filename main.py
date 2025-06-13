from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import RPCError
from typing import List, Dict
from io import BytesIO
import os
import logging
import mimetypes
from concurrent.futures import ThreadPoolExecutor
import asyncio
import re

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
API_ID = int(os.getenv("API_ID", "28437242"))
API_HASH = os.getenv("API_HASH", "25ff44a57d1be2775b5fb60278ef724b")
STRING_SESSION = os.getenv("STRING_SESSION")
CHANNEL = os.getenv("CHANNEL", "https://t.me/+yGEhMlthGkIxM2Rl")

# Validate configuration
if not STRING_SESSION:
    raise ValueError("STRING_SESSION environment variable is required")

executor = ThreadPoolExecutor(max_workers=4)

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
channel_entity = None

app = FastAPI(
    title="Telegram Media API",
    description="Efficient media streaming via Telegram",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

mimetypes.init()
mimetypes.add_type('video/webm', '.webm')
mimetypes.add_type('video/quicktime', '.mov')

@app.on_event("startup")
async def startup():
    global channel_entity
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise ValueError("Telegram client authorization failed")
        channel_entity = await client.get_entity(CHANNEL)
        logger.info("Telegram client started successfully")
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Startup failed: {str(e)}")

@app.on_event("shutdown")
async def shutdown():
    try:
        await client.disconnect()
        executor.shutdown(wait=True)
        logger.info("Telegram client and resources cleaned up")
    except Exception as e:
        logger.error(f"Shutdown failed: {str(e)}")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        data = await file.read()
        if not data:
            raise HTTPException(400, "Empty file")
        if len(data) > 2 * 1024 * 1024 * 1024:
            raise HTTPException(413, "File too large")

        msg = await client.send_file(
            channel_entity,
            BytesIO(data),
            file_name=file.filename,
            caption=file.filename,
            part_size_kb=512,
            workers=4,
            attributes=[DocumentAttributeFilename(file.filename)]
        )
        return {"id": msg.id, "name": file.filename, "status": "success"}
    except RPCError as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(500, f"Upload failed: {str(e)}")
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(500, "Internal server error")

@app.get("/files")
async def list_files(limit: int = 100):
    try:
        if limit <= 0 or limit > 1000:
            raise HTTPException(400, "Invalid limit parameter")
            
        messages = await client.get_messages(channel_entity, limit=limit)
        files: List[Dict] = []
        
        for msg in messages:
            if not msg.media or not hasattr(msg.media, "document"):
                continue
            doc = msg.media.document
            filename = next(
                (a.file_name for a in doc.attributes if isinstance(a, DocumentAttributeFilename)),
                msg.message or f"file_{msg.id}"
            )
            files.append({
                "id": msg.id,
                "name": filename,
                "mime_type": doc.mime_type or "application/octet-stream",
                "size": doc.size or 0
            })
        return JSONResponse(content=files)
    except RPCError as e:
        logger.error(f"List failed: {str(e)}")
        raise HTTPException(500, f"List failed: {str(e)}")
    except Exception as e:
        logger.error(f"List failed: {str(e)}")
        raise HTTPException(500, "Failed to retrieve files")

@app.get(
    "/stream/{msg_id}",
    responses={
        206: {
            "content": {},
            "description": "Partial content for range requests"
        },
        200: {
            "content": {},
            "description": "Full file content"
        }
    }
)
async def stream_file(msg_id: int, request: Request):
    try:
        msg = await client.get_messages(channel_entity, ids=msg_id)
        msg = msg[0] if isinstance(msg, list) else msg
        if not msg or not msg.media or not hasattr(msg.media, "document"):
            raise HTTPException(404, "File not found")

        doc = msg.media.document
        file_name = next(
            (a.file_name for a in doc.attributes if isinstance(a, DocumentAttributeFilename)),
            f"file_{msg.id}"
        )
        file_size = doc.size or 0
        mime_type = doc.mime_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        range_header = request.headers.get("range")

        if range_header and file_size:
            match = re.match(r"bytes\s*=\s*(\d+)-(\d*)", range_header)
            if not match:
                raise HTTPException(416, "Invalid range")

            start, end = match.groups()
            start = int(start)
            end = int(end) if end else file_size - 1

            if start >= file_size:
                raise HTTPException(416, "Range not satisfiable")

            content_length = min(end, file_size - 1) - start + 1

            async def ranged_stream():
                async for chunk in client.iter_download(msg.media, offset=start, limit=content_length):
                    yield chunk

            return StreamingResponse(
                ranged_stream(),
                status_code=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(content_length),
                    "Accept-Ranges": "bytes"
                },
                media_type=mime_type
            )

        async def full_stream():
            async for chunk in client.iter_download(msg.media):
                yield chunk

        return StreamingResponse(
            full_stream(),
            headers={
                "Content-Type": mime_type,
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400"
            },
            media_type=mime_type
        )

    except RPCError as e:
        logger.error(f"Stream failed: {str(e)}")
        raise HTTPException(500, f"Stream failed: {str(e)}")
    except Exception as e:
        logger.error(f"Stream failed: {str(e)}")
        raise HTTPException(500, "Internal server error")

@app.delete("/delete/{msg_id}")
async def delete_file(msg_id: int):
    try:
        await client.delete_messages(channel_entity, message_ids=[msg_id])
        return {"status": "deleted"}
    except RPCError as e:
        logger.error(f"Delete failed: {str(e)}")
        raise HTTPException(500, f"Delete failed: {str(e)}")
    except Exception as e:
        logger.error(f"Delete failed: {str(e)}")
        raise HTTPException(500, "Internal server error")