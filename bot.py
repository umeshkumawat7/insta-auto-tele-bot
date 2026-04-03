import requests
import os
import re
import threading
from typing import Optional, List, Dict

# Default caption drives traffic via "link in bio" without referencing specific content.
# Keeps posts compliant with Instagram community guidelines.
DEFAULT_CAPTION = """🔗 Link in bio

✨ Save this for later
📲 Follow for more

#linkinbio #explore #trending #viral #reels #foryou #fyp #instareels #reelsinstagram #explorepage"""

pending_caption_edit = {}  # {chat_id: post_id} — tracks users currently editing caption

BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API = os.getenv("TELEGRAM_API", "https://api.telegram.org/bot")

MEDIA_BUFFER = {}

def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> dict:
    url = f"{TELEGRAM_API}{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    return requests.post(url, json=data).json()

def send_photo(chat_id: int, photo: str) -> dict:
    url = f"{TELEGRAM_API}{BOT_TOKEN}/sendPhoto"
    data = {"chat_id": chat_id, "photo": photo}
    return requests.post(url, json=data).json()

def send_video(chat_id: int, video: str) -> dict:
    url = f"{TELEGRAM_API}{BOT_TOKEN}/sendVideo"
    data = {"chat_id": chat_id, "video": video}
    return requests.post(url, json=data).json()

def answer_callback(callback_query_id: str, text: str = "✅") -> None:
    url = f"{TELEGRAM_API}{BOT_TOKEN}/answerCallbackQuery"
    data = {"callback_query_id": callback_query_id, "text": text}
    requests.post(url, json=data)

def edit_message_text(chat_id: int, message_id: int, text: str) -> None:
    url = f"{TELEGRAM_API}{BOT_TOKEN}/editMessageText"
    data = {"chat_id": chat_id, "message_id": message_id, "text": text}
    requests.post(url, json=data)

def extract_url(text: str) -> Optional[str]:
    match = re.search(r'https?://[^\s]+', text)
    return match.group(0) if match else None

def get_file_url(file_id: str) -> str:
    url = f"{TELEGRAM_API}{BOT_TOKEN}/getFile?file_id={file_id}"
    response = requests.get(url).json()
    if response.get("ok"):
        file_path = response["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    return ""

def parse_update(data: dict) -> dict:
    result = {
        "type": "message",
        "chat_id": None,
        "message_id": None,
        "text": None,
        "caption": None,
        "url": None,
        "file_id": None,
        "file_type": None,
        "file_ids": None,
        "media_group_id": None,
        "callback_query_id": None,
        "callback_data": None,
        "post_id": None,
    }
    
    if "callback_query" in data:
        callback = data["callback_query"]
        
        # Intercept the "edit_" callback so main.py doesn't overwrite it
        cb_data = callback.get("data")
        if cb_data and cb_data.startswith("edit_"):
            chat_id = callback["message"]["chat"]["id"]
            post_id = int(cb_data.split("_")[1])
            answer_callback(callback["id"], "Send your new caption now.")
            send_message(chat_id, "✏️ Send your new caption now.\nYour next message will replace the current caption.")
            pending_caption_edit[chat_id] = post_id
            
            # Return dummy callback to stop main.py from complaining or sending help message
            result["type"] = "callback"
            result["chat_id"] = chat_id
            result["callback_query_id"] = callback["id"]
            result["callback_data"] = "handled_in_bot"
            return result

        result["type"] = "callback"
        result["chat_id"] = callback["message"]["chat"]["id"]
        result["message_id"] = callback["message"]["message_id"]
        result["callback_query_id"] = callback["id"]
        result["callback_data"] = cb_data
        return result
    
    message = data.get("message", {})
    result["chat_id"] = message["chat"]["id"]
    result["message_id"] = message["message_id"]
    result["text"] = message.get("text")
    result["caption"] = message.get("caption")
    
    chat_id = result["chat_id"]
    message_text = result["text"]
    
    # User editing caption check BEFORE URL extraction
    if chat_id in pending_caption_edit and message_text:
        post_id = pending_caption_edit.pop(chat_id)
        new_caption = message_text.strip()
        
        # Update caption in DB for this post_id
        from database import update_caption, get_post
        update_caption(post_id, new_caption)
        
        # Re-fetch post and re-send preview message with updated caption and buttons
        post = get_post(post_id)
        send_message(chat_id, f"✅ Caption updated!\n\n📝 New Caption:\n{new_caption}")
        send_inline_keyboard(chat_id, post_id)
        
        # Return a dummy callback event to cleanly stop main.py from processing this message
        result["type"] = "callback"
        result["callback_data"] = "handled_in_bot"
        result["url"] = None
        result["file_id"] = None
        return result
    
    if result["text"]:
        result["url"] = extract_url(result["text"])
        # Fix: when creating a new post from a URL, 
        # ensure DEFAULT_CAPTION is used instead of the raw URL
        if result["url"] and result["text"].strip() == result["url"]:
            result["text"] = DEFAULT_CAPTION
        
    # Use DEFAULT_CAPTION if no caption provided
    if not result["caption"]:
        result["caption"] = DEFAULT_CAPTION
    
    if "photo" in message:
        result["file_type"] = "photo"
        result["file_id"] = message["photo"][-1]["file_id"]
    elif "video" in message:
        result["file_type"] = "video"
        result["file_id"] = message["video"]["file_id"]
    elif "document" in message:
        doc = message["document"]
        mime_type = doc.get("mime_type", "")
        if mime_type.startswith("image/") or mime_type.startswith("video/"):
            result["file_type"] = "document"
            result["file_id"] = doc["file_id"]
    
    result["media_group_id"] = message.get("media_group_id")
    
    return result

def send_preview_with_buttons(chat_id: int, post_id: int, post_type: str, file_paths: list, caption: str = "") -> None:
    """Send media preview with inline buttons for approval"""
    from media_detector import is_image, is_video
    from database import get_post
    
    # Create inline keyboard
    keyboard = {
        "inline_keyboard": [[
            {"text": "✏️ Edit Caption", "callback_data": f"edit_{post_id}"},
            {"text": "✅ Post Now", "callback_data": f"post_{post_id}"},
            {"text": "❌ Cancel", "callback_data": f"cancel_{post_id}"}
        ]]
    }
    
    # Send preview message
    post = get_post(post_id)
    caption_to_show = post.caption if post and post.caption else DEFAULT_CAPTION
    message = f"✅ Ready to post\nType: {post_type}\n\n📝 Caption:\n{caption_to_show}\n\nChoose an action:"

    if post_type == "CAROUSEL":
        # Send first image with album info
        send_photo(chat_id, file_paths[0])
    elif is_image(file_paths[0]):
        send_photo(chat_id, file_paths[0])
    else:
        send_video(chat_id, file_paths[0])
    
    # Send message with buttons
    url = f"{TELEGRAM_API}{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": keyboard
    }
    requests.post(url, json=data).json()

def send_inline_keyboard(chat_id: int, post_id: int) -> None:
    keyboard = {
        "inline_keyboard": [[
            {"text": "✏️ Edit Caption", "callback_data": f"edit_{post_id}"},
            {"text": "✅ Post Now", "callback_data": f"post_{post_id}"},
            {"text": "❌ Cancel", "callback_data": f"cancel_{post_id}"}
        ]]
    }
    url = f"{TELEGRAM_API}{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": "Choose an action:", "reply_markup": keyboard}
    requests.post(url, json=data)

def buffer_album_item(media_group_id: str, chat_id: int, file_id: str, file_type: str, caption: str):
    if media_group_id not in MEDIA_BUFFER:
        MEDIA_BUFFER[media_group_id] = {
            "items": [],
            "chat_id": chat_id,
            "caption": caption,
            "timer": None
        }
    
    buffer = MEDIA_BUFFER[media_group_id]
    if buffer["timer"]:
        buffer["timer"].cancel()
    
    buffer["items"].append({"file_id": file_id, "file_type": file_type})
    
    buffer["timer"] = threading.Timer(2.0, flush_album, args=[media_group_id])
    buffer["timer"].start()

def flush_album(media_group_id: str) -> dict:
    if media_group_id not in MEDIA_BUFFER:
        return {}
    
    buffer = MEDIA_BUFFER.pop(media_group_id)
    return {
        "type": "album",
        "chat_id": buffer["chat_id"],
        "file_ids": [item["file_id"] for item in buffer["items"]],
        "caption": buffer["caption"]
    }
