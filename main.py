import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import InputMessagesFilterDocument, InputMessagesFilterPhotos

# 🔐 Telegram credentials
api_id = 28437242
api_hash = "25ff44a57d1be2775b5fb60278ef724b"
string = os.environ.get("STRING_SESSION")  # Make sure this is set
channel = 'https://t.me/+yGEhMlthGkIxM2Rl'  # your private channel invite link

client = TelegramClient(StringSession(string), api_id, api_hash)


async def method1():
    """1. iter_messages, no filter"""
    files = []
    async for msg in client.iter_messages(channel, limit=20):
        if msg.media:
            path = await msg.download_media()
            files.append(path)
    return files


async def method2():
    """2. get_messages, no filter"""
    files = []
    msgs = await client.get_messages(channel, limit=20)
    for msg in msgs:
        if msg.media:
            path = await msg.download_media()
            files.append(path)
    return files


async def method3():
    """3. iter_messages with Document filter"""
    files = []
    async for msg in client.iter_messages(channel, filter=InputMessagesFilterDocument, limit=20):
        if msg.media:
            path = await msg.download_media()
            files.append(path)
    return files


async def method4():
    """4. iter_messages with Photos filter"""
    files = []
    async for msg in client.iter_messages(channel, filter=InputMessagesFilterPhotos, limit=20):
        if msg.media:
            path = await msg.download_media()
            files.append(path)
    return files


async def main():
    await client.start()

    methods = [method1, method2, method3, method4]
    for i, method in enumerate(methods, start=1):
        try:
            files = await method()
            if files:
                print(f"\nMethod {i}: ✅ Success - Downloaded {len(files)} file(s)")
                for f in files:
                    print(f"  → {f}")
            else:
                print(f"\nMethod {i}: ⚠️ No media found")
        except Exception as e:
            print(f"\nMethod {i}: ❌ Failed ({e})")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())