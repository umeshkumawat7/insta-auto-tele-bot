from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
import os
import json
import logging
from dotenv import load_dotenv

from database import init_db, create_post, update_status, update_file_paths, get_post, delete_post
from bot import parse_update, send_message, send_preview_with_buttons, answer_callback, buffer_album_item, flush_album
from downloader import download_from_url, download_from_telegram, download_and_upload_all
from media_detector import detect_post_type, validate_for_instagram
from instagram import publish

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

ALLOWED_CHAT_ID = int(os.getenv("ALLOWED_CHAT_ID", "0"))

app = FastAPI(title="Instagram Auto Post Bot", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        logger.info("✅ Database initialised")
    except Exception as e:
        logger.error(f"❌ Database init failed: {e}")
    os.makedirs("downloads", exist_ok=True)
    logger.info("✅ Downloads directory ready")


@app.post("/webhook")
async def webhook(data: dict, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_update, data)
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


def process_update(data: dict):
    logger.info("🔄 Processing update...")
    try:
        update = parse_update(data)

        chat_id = update.get("chat_id")
        if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
            logger.warning(f"🚫 Blocked unauthorised chat_id: {chat_id}")
            send_message(chat_id, "⛔ You are not authorised to use this bot.")
            return

        if update.get("callback_data") == "handled_in_bot":
            return

        if update.get("media_group_id"):
            buffer_album_item(
                update["media_group_id"],
                update["chat_id"],
                update["file_id"],
                update["file_type"],
                update.get("caption") or "",
            )
            return

        if update["type"] == "callback":
            handle_callback(update)
            return

        if update["type"] == "album":
            handle_album(update)
            return

        if update.get("file_id"):
            handle_single_file(update)
            return

        if update.get("url"):
            handle_url(update)
            return

        send_message(
            update["chat_id"],
            "👋 Send a photo, video, URL, or album to post to Instagram.\n\n"
            "💡 Tip: Add 'reel', 'story', or 'carousel' in your message to choose the post type.",
        )

    except Exception as e:
        logger.error(f"❌ process_update error: {e}", exc_info=True)
        try:
            send_message(update["chat_id"], "⚠️ Something went wrong. Please try again.")
        except Exception:
            pass


def handle_single_file(update: dict):
    chat_id = update["chat_id"]
    send_message(chat_id, "⏳ Processing your file...")
    local_path = None
    try:
        local_path = download_from_telegram(update["file_id"])
        post_type = detect_post_type([local_path], update.get("caption") or "")
        validate_for_instagram(local_path, post_type)
        cloudinary_url = download_and_upload_all(
            [{"type": "file_id", "value": update["file_id"]}]
        )[0]
        post = create_post(chat_id, update["file_id"], post_type, update.get("caption") or "")
        update_file_paths(post.id, [local_path], [cloudinary_url])
        send_preview_with_buttons(chat_id, post.id, post_type, [cloudinary_url], update.get("caption") or "")
    except Exception as e:
        logger.error(f"❌ handle_single_file: {e}", exc_info=True)
        if local_path and os.path.exists(local_path):
            os.remove(local_path)
        send_message(chat_id, f"❌ {e}")


def handle_url(update: dict):
    chat_id = update["chat_id"]
    send_message(chat_id, "⏳ Downloading from URL...")
    local_path = None
    try:
        local_path = download_from_url(update["url"])
        post_type = detect_post_type([local_path], update.get("text") or "")
        validate_for_instagram(local_path, post_type)
        cloudinary_url = download_and_upload_all(
            [{"type": "url", "value": update["url"]}]
        )[0]
        post = create_post(chat_id, update["url"], post_type, update.get("text") or "")
        update_file_paths(post.id, [local_path], [cloudinary_url])
        send_preview_with_buttons(chat_id, post.id, post_type, [cloudinary_url], update.get("text") or "")
    except Exception as e:
        logger.error(f"❌ handle_url: {e}", exc_info=True)
        if local_path and os.path.exists(local_path):
            os.remove(local_path)
        send_message(chat_id, f"❌ {e}")


def handle_album(update: dict):
    chat_id = update["chat_id"]
    try:
        sources = [{"type": "file_id", "value": fid} for fid in update["file_ids"]]
        cloudinary_urls = download_and_upload_all(sources)
        post_type = "CAROUSEL"
        post = create_post(chat_id, json.dumps(update["file_ids"]), post_type, update.get("caption") or "")
        update_file_paths(post.id, cloudinary_urls, cloudinary_urls)
        send_preview_with_buttons(chat_id, post.id, post_type, cloudinary_urls, update.get("caption") or "")
    except Exception as e:
        logger.error(f"❌ handle_album: {e}", exc_info=True)
        send_message(chat_id, f"❌ {e}")


def handle_callback(update: dict):
    answer_callback(update["callback_query_id"], "Processing...")
    cb = update["callback_data"]
    if "_" not in cb:
        return
    action, raw_id = cb.split("_", 1)
    if not raw_id.isdigit():
        return
    post_id = int(raw_id)
    if action == "post":
        update_status(post_id, "approved")
        publish_to_instagram(post_id, update["chat_id"])
    elif action == "cancel":
        delete_post(post_id)
        send_message(update["chat_id"], "🗑️ Cancelled. Post deleted.")


def publish_to_instagram(post_id: int, chat_id: int):
    post = get_post(post_id)
    if not post:
        send_message(chat_id, "❌ Post not found.")
        return
    try:
        urls = json.loads(post.public_urls)
        logger.info(f"🚀 Publishing {post.post_type} — {len(urls)} item(s)")
        media_id = publish(post.post_type, urls, post.caption or "")
        update_status(post_id, "posted", ig_media_id=media_id)
        send_message(
            chat_id,
            f"🎉 <b>Posted to Instagram!</b>\n"
            f"Type: {post.post_type}\n"
            f"Media ID: <code>{media_id}</code>",
        )
    except Exception as e:
        logger.error(f"❌ publish_to_instagram: {e}", exc_info=True)
        update_status(post_id, "failed")
        send_message(chat_id, f"❌ Publish failed: {e}")
