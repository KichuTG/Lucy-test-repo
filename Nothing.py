utils.py

import asyncio import logging from info import DBX_CHANNEL from ia_filterdb import Media, Media2, progress_collection from pyrogram.errors import FloodWait

logger = logging.getLogger(name)

async def get_all_files(): async for file in Media.find({}).sort("$natural", 1): yield 'primary', file async for file in Media2.find({}).sort("$natural", 1): yield 'secondary', file

async def send_all_files(bot): sent = await progress_collection.find_one({'_id': 'progress'}) sent = sent['index'] if sent else 0

files = []
async for db_type, file in get_all_files():
    files.append((db_type, file))

total = len(files)
if total == 0:
    logger.info("No files to send.")
    return

logger.info(f"Starting to send {total} files to DBX_CHANNEL...")

for index in range(sent, total):
    db_type, file = files[index]

    try:
        await bot.send_document(
            chat_id=DBX_CHANNEL,
            document=file.file_id,
            caption=file.caption or "",
            file_name=file.file_name
        )
    except FloodWait as e:
        logger.warning(f"FloodWait for {e.value} seconds")
        await asyncio.sleep(e.value)
        continue
    except Exception as e:
        logger.exception(f"Failed to send file at index {index}: {e}")
        continue

    if (index + 1) % 30 == 0:
        logger.info(f"Sent {index + 1} of {total} files, sleeping for 40 seconds...")
        await asyncio.sleep(40)

    await progress_collection.update_one(
        {"_id": "progress"},
        {"$set": {"index": index + 1, "total": total}},
        upsert=True
    )

logger.info("✅ All files sent successfully.")
await bot.send_message(DBX_CHANNEL, "Successfully completed 🎊")

commands.py

from pyrogram import filters from pyrogram.types import Message from utils import send_all_files from info import DBX_CHANNEL

@app.on_message(filters.command("sendallfiles") & filters.chat(DBX_CHANNEL)) async def trigger_send_all_files(client, message: Message): await message.reply("✅ Sending all files, progress will be printed in logs...") asyncio.create_task(send_all_files(client))

ia_filterdb.py (add this line)

progress_collection = db["sendall_progress"]

In bot startup (e.g. bot.py or main.py)

async def log_progress(): while True: data = await progress_collection.find_one({'_id': 'progress'}) if data: index = data.get('index', 0) total = data.get('total', 1) percent = (index / total) * 100 logger.info(f"SendAll Progress: {index}/{total} ({percent:.2f}%)") await asyncio.sleep(1800)  # every 30 minutes

Run this in on_startup

asyncio.create_task(log_progress())

