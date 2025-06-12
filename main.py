from fastapi import FastAPI, UploadFile
from telethon import TelegramClient
from telethon.sessions import StringSession
import os
import asyncio

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
    await client.send_file(channel_id, data, file_name=name, caption=name)
    return {"status": "uploaded", "filename": name}
