
# @Shrimadhav Uk | @LISA_FAN_LK
import os
import logging
import asyncio
import aiohttp
import json
import math
import shutil
import time
from datetime import datetime
from plugins.config import Config
from plugins.script import Translation
from plugins.thumbnail import *
from plugins.database.database import db
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes, TimeFormatter
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image
from pyrogram import enums

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

def split_file(file_path, max_size=2000 * 1024 * 1024):
    with open(file_path, "rb") as f:
        file_name = os.path.basename(file_path)
        part_num = 1
        while chunk := f.read(max_size):
            part_file_name = f"{file_name}.part{part_num}"
            with open(part_file_name, "wb") as part_file:
                part_file.write(chunk)
            part_num += 1
    return [f"{file_name}.part{num}" for num in range(1, part_num)]

async def ddl_call_back(bot, update):
    logger.info(update)
    cb_data = update.data
    tg_send_type, youtube_dl_format, youtube_dl_ext = cb_data.split("=")
    thumb_image_path = os.path.join(Config.DOWNLOAD_LOCATION, f"{update.from_user.id}.jpg")
    youtube_dl_url = update.message.reply_to_message.text
    custom_file_name = os.path.basename(youtube_dl_url.strip())

    if "|" in youtube_dl_url:
        parts = youtube_dl_url.split("|")
        if len(parts) == 2:
            youtube_dl_url, custom_file_name = parts[0].strip(), parts[1].strip()
    else:
        for entity in update.message.reply_to_message.entities:
            if entity.type == "text_link":
                youtube_dl_url = entity.url
            elif entity.type == "url":
                o = entity.offset
                l = entity.length
                youtube_dl_url = youtube_dl_url[o:o + l]

    description = Translation.CUSTOM_CAPTION_UL_FILE
    start = datetime.now()
    await update.message.edit_caption(caption=Translation.DOWNLOAD_START, parse_mode=enums.ParseMode.HTML)

    tmp_user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(update.from_user.id))
    os.makedirs(tmp_user_dir, exist_ok=True)
    download_path = os.path.join(tmp_user_dir, custom_file_name)

    async with aiohttp.ClientSession() as session:
        c_time = time.time()
        try:
            await download_coroutine(bot, session, youtube_dl_url, download_path, update.message.chat.id, update.message.id, c_time)
        except asyncio.TimeoutError:
            await bot.edit_message_text(text=Translation.SLOW_URL_DECED, chat_id=update.message.chat.id, message_id=update.message.id)
            return

    if os.path.exists(download_path):
        end_one = datetime.now()
        await update.message.edit_caption(caption=Translation.UPLOAD_START, parse_mode=enums.ParseMode.HTML)
        try:
            file_size = os.stat(download_path).st_size
        except FileNotFoundError:
            download_path = os.path.splitext(download_path)[0] + ".mkv"
            file_size = os.stat(download_path).st_size

        start_time = time.time()

        if file_size > Config.TG_MAX_FILE_SIZE:
            split_files = split_file(download_path)
            for part in split_files:
                await update.message.reply_document(
                    document=part,
                    caption=description,
                    parse_mode=enums.ParseMode.HTML,
                    progress=progress_for_pyrogram,
                    progress_args=(Translation.UPLOAD_START, update.message, start_time)
                )
                os.remove(part)
        else:
            if not await db.get_upload_as_doc(update.from_user.id):
                thumbnail = await Gthumb01(bot, update)
                await update.message.reply_document(
                    document=download_path,
                    thumb=thumbnail,
                    caption=description,
                    parse_mode=enums.ParseMode.HTML,
                    progress=progress_for_pyrogram,
                    progress_args=(Translation.UPLOAD_START, update.message, start_time)
                )
            else:
                if tg_send_type == "audio":
                    duration = await Mdata03(download_path)
                    thumbnail = await Gthumb01(bot, update)
                    await update.message.reply_audio(
                        audio=download_path,
                        caption=description,
                        parse_mode=enums.ParseMode.HTML,
                        duration=duration,
                        thumb=thumbnail,
                        progress=progress_for_pyrogram,
                        progress_args=(Translation.UPLOAD_START, update.message, start_time)
                    )
                elif tg_send_type == "vm":
                    width, duration = await Mdata02(download_path)
                    thumb_image_path = await Gthumb02(bot, update, duration, download_path)
                    await update.message.reply_video_note(
                        video_note=download_path,
                        duration=duration,
                        length=width,
                        thumb=thumb_image_path,
                        progress=progress_for_pyrogram,
                        progress_args=(Translation.UPLOAD_START, update.message, start_time)
                    )
                else:
                    width, height, duration = await Mdata01(download_path)
                    thumb_image_path = await Gthumb02(bot, update, duration, download_path)
                    await update.message.reply_video(
                        video=download_path,
                        caption=description,
                        duration=duration,
                        width=width,
                        height=height,
                        supports_streaming=True,
                        parse_mode=enums.ParseMode.HTML,
                        thumb=thumb_image_path,
                        progress=progress_for_pyrogram,
                        progress_args=(Translation.UPLOAD_START, update.message, start_time)
                    )
        end_two = datetime.now()
        try:
            os.remove(download_path)
            os.remove(thumb_image_path)
        except:
            pass

        await update.message.edit_caption(
            caption=Translation.AFTER_SUCCESSFUL_UPLOAD_MSG_WITH_TS.format((end_one - start).seconds, (end_two - end_one).seconds),
            parse_mode=enums.ParseMode.HTML
        )
    else:
        await update.message.edit_caption(caption=Translation.NO_VOID_FORMAT_FOUND.format("Incorrect Link"), parse_mode=enums.ParseMode.HTML)

async def download_coroutine(bot, session, url, file_name, chat_id, message_id, start):
    downloaded = 0
    display_message = ""
    async with session.get(url, timeout=Config.PROCESS_MAX_TIMEOUT) as response:
        total_length = int(response.headers["Content-Length"])
        content_type = response.headers["Content-Type"]
        if "text" in content_type and total_length < 500:
            return await response.release()
        await bot.edit_message_text(chat_id, message_id, text=f"Initiating Download\\nURL: {url}\\nFile Size: {humanbytes(total_length)}")
        with open(file_name, "wb") as f_handle:
            while True:
                chunk = await response.content.read(Config.CHUNK_SIZE)
                if not chunk:
                    break
                f_handle.write(chunk)
                downloaded += Config.CHUNK_SIZE
                now = time.time()
                diff = now - start
                if round(diff % 5.00) == 0 or downloaded == total_length:
                    percentage = downloaded * 100 / total_length
                    speed = downloaded / diff
                    elapsed_time = round(diff) * 1000
                    time_to_completion = round((total_length - downloaded) / speed) * 1000
                    estimated_total_time = elapsed_time + time_to_completion
                    try:
                        current_message = f"**Download Status**\\nURL: {url}\\nFile Size: {humanbytes(total_length)}\\nDownloaded: {humanbytes(downloaded)}\\nETA: {TimeFormatter(estimated_total_time)}"
                        if current_message != display_message:
                            await bot.edit_message_text(chat_id, message_id, text=current_message)
                            display_message = current_message
                    except Exception as e:
                        logger.info(str(e))
        return await response.release()

  
