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

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Instagram Auto Post Bot")

@app.on_event("startup")
async def startup_event():
    try:
        from database import init_db
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    os.makedirs("downloads", exist_ok=True)
    logger.info("Downloads directory created/verified")

@app.post("/webhook")
async def webhook(data: dict, background_tasks: BackgroundTasks):
    logger.info(f"📥 Incoming webhook: {json.dumps(data, indent=2)}")
    background_tasks.add_task(process_update, data)
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0"}

def process_update(data: dict):
    logger.info("🔄 Starting update processing...")
    try:
        update = parse_update(data)
        logger.info(f"📝 Parsed update: {json.dumps(update, indent=2)}")
        
        # Handle album buffering
        if update.get("media_group_id"):
            logger.info(f"📸 Album buffering for group: {update['media_group_id']}")
            buffer_album_item(
                update["media_group_id"],
                update["chat_id"],
                update["file_id"],
                update["file_type"],
                update["caption"] or ""
            )
            return
        
        # Handle callback queries
        if update["type"] == "callback":
            logger.info(f"🔘 Callback received: {update['callback_data']}")
            handle_callback(update)
            return
        
        # Handle album flush
        if update["type"] == "album":
            logger.info(f"🎊 Album flush: {len(update['file_ids'])} items")
            handle_album(update)
            return
        
        # Handle single file
        if update["file_id"]:
            logger.info(f"📁 Single file: {update['file_id']} ({update['file_type']})")
            handle_single_file(update)
            return
        
        # Handle URL
        if update["url"]:
            logger.info(f"🔗 URL detected: {update['url']}")
            handle_url(update)
            return
        
        # No media, no URL
        logger.info("💬 No media/URL - sending help message")
        send_message(
            update["chat_id"],
            "👋 Send a photo, video, URL, or album to post to Instagram.\n\nTip: Add 'reel', 'story', or 'carousel' to your message to choose post type."
        )
        
    except Exception as e:
        logger.error(f"❌ Error processing update: {e}", exc_info=True)
        if "chat_id" in locals():
            send_message(update["chat_id"], "⚠️ Something went wrong. Please try again.")

def handle_single_file(update: dict):
    logger.info(f"📥 Processing single file for chat {update['chat_id']}")
    send_message(update["chat_id"], "⏳ Processing your file...")
    
    try:
        # Download file
        logger.info(f"⬇️ Downloading file: {update['file_id']}")
        local_path = download_from_telegram(update["file_id"])
        logger.info(f"✅ File downloaded to: {local_path}")
        
        # Detect post type
        post_type = detect_post_type([local_path], update["caption"] or "")
        logger.info(f"🎯 Detected post type: {post_type}")
        
        # Validate for Instagram
        logger.info(f"🔍 Validating file for Instagram...")
        validate_for_instagram(local_path, post_type)
        logger.info("✅ File validation passed")
        
        # Upload to Cloudinary
        logger.info("☁️ Uploading to Cloudinary...")
        cloudinary_url = download_and_upload_all([{"type": "file_id", "value": update["file_id"]}])[0]
        logger.info(f"✅ Cloudinary URL: {cloudinary_url}")
        
        # Create post record
        logger.info("💾 Creating post record...")
        post = create_post(
            update["chat_id"],
            update["file_id"],
            post_type,
            update["caption"] or ""
        )
        logger.info(f"✅ Post created with ID: {post.id}")
        
        # Update file paths
        update_file_paths(post.id, [local_path], [cloudinary_url])
        logger.info("📝 File paths updated")
        
        # Send preview
        logger.info("👀 Sending preview with buttons...")
        send_preview_with_buttons(
            update["chat_id"],
            post.id,
            post_type,
            [local_path],
            update["caption"] or ""
        )
        logger.info("✅ Preview sent successfully")
        
    except Exception as e:
        logger.error(f"❌ Error in handle_single_file: {e}", exc_info=True)
        # Clean up on error
        if 'local_path' in locals() and os.path.exists(local_path):
            os.remove(local_path)
            logger.info(f"🗑️ Cleaned up file: {local_path}")
        send_message(update["chat_id"], f"❌ {str(e)}")

def handle_url(update: dict):
    logger.info(f"🌐 Processing URL for chat {update['chat_id']}")
    send_message(update["chat_id"], "⏳ Downloading from URL...")
    
    try:
        # Download file
        logger.info(f"⬇️ Downloading from URL: {update['url']}")
        local_path = download_from_url(update["url"])
        logger.info(f"✅ File downloaded to: {local_path}")
        
        # Detect post type
        post_type = detect_post_type([local_path], update["text"] or "")
        logger.info(f"🎯 Detected post type: {post_type}")
        
        # Validate for Instagram
        logger.info(f"🔍 Validating file for Instagram...")
        validate_for_instagram(local_path, post_type)
        logger.info("✅ File validation passed")
        
        # Upload to Cloudinary
        logger.info("☁️ Uploading to Cloudinary...")
        cloudinary_url = download_and_upload_all([{"type": "url", "value": update["url"]}])[0]
        logger.info(f"✅ Cloudinary URL: {cloudinary_url}")
        
        # Create post record
        logger.info("💾 Creating post record...")
        post = create_post(
            update["chat_id"],
            update["url"],
            post_type,
            update["text"] or ""
        )
        logger.info(f"✅ Post created with ID: {post.id}")
        
        # Update file paths
        update_file_paths(post.id, [local_path], [cloudinary_url])
        logger.info("📝 File paths updated")
        
        # Send preview
        logger.info("👀 Sending preview with buttons...")
        send_preview_with_buttons(
            update["chat_id"],
            post.id,
            post_type,
            [local_path],
            update["text"] or ""
        )
        logger.info("✅ Preview sent successfully")
        
    except Exception as e:
        logger.error(f"❌ Error in handle_url: {e}", exc_info=True)
        # Clean up on error
        if 'local_path' in locals() and os.path.exists(local_path):
            os.remove(local_path)
            logger.info(f"🗑️ Cleaned up file: {local_path}")
        send_message(update["chat_id"], f"❌ {str(e)}")

def handle_album(update: dict):
    logger.info(f"🎊 Processing album for chat {update['chat_id']}")
    try:
        # Download all files
        sources = [{"type": "file_id", "value": file_id} for file_id in update["file_ids"]]
        logger.info(f"📦 Downloading {len(sources)} files...")
        local_paths = download_and_upload_all(sources)
        logger.info(f"✅ Files downloaded: {local_paths}")
        
        # Detect post type (should be CAROUSEL)
        post_type = detect_post_type(local_paths, update["caption"] or "")
        logger.info(f"🎯 Detected post type: {post_type}")
        
        # Validate all files
        logger.info("🔍 Validating all files for Instagram...")
        for i, path in enumerate(local_paths):
            validate_for_instagram(path, post_type)
            logger.info(f"✅ File {i+1} validation passed")
        
        # Create post record
        logger.info("💾 Creating post record...")
        post = create_post(
            update["chat_id"],
            json.dumps(update["file_ids"]),
            post_type,
            update["caption"] or ""
        )
        logger.info(f"✅ Post created with ID: {post.id}")
        
        # Update file paths
        update_file_paths(post.id, local_paths, local_paths)  # Cloudinary URLs returned
        logger.info("📝 File paths updated")
        
        # Send preview
        logger.info("👀 Sending preview with buttons...")
        send_preview_with_buttons(
            update["chat_id"],
            post.id,
            post_type,
            local_paths,
            update["caption"] or ""
        )
        logger.info("✅ Preview sent successfully")
        
    except Exception as e:
        logger.error(f"❌ Error in handle_album: {e}", exc_info=True)
        send_message(update["chat_id"], f"❌ {str(e)}")

def handle_callback(update: dict):
    logger.info(f"🔘 Processing callback: {update['callback_data']}")
    answer_callback(update["callback_query_id"], "Processing...")
    
    callback_data = update["callback_data"]
    post_id = int(callback_data.split("_")[1])
    logger.info(f"📋 Post ID from callback: {post_id}")
    
    if "post_" in callback_data:
        logger.info("✅ User approved post - publishing to Instagram...")
        # Approve and publish
        update_status(post_id, "approved")
        # Background task to publish to Instagram
        publish_to_instagram(post_id, update["chat_id"])
        
    elif "cancel_" in callback_data:
        logger.info("❌ User cancelled post - cleaning up...")
        # Cancel and delete
        delete_post(post_id)
        send_message(update["chat_id"], "🗑️ Cancelled and cleaned up.")

def publish_to_instagram(post_id: int, chat_id: int):
    logger.info(f"🚀 Starting Instagram publish for post {post_id}")
    post = get_post(post_id)
    if not post:
        logger.error(f"❌ Post {post_id} not found")
        return
    
    try:
        urls = json.loads(post.public_urls)
        logger.info(f"📤 Publishing {post.post_type} with {len(urls)} media items")
        media_id = publish(post.post_type, urls, post.caption or "")
        logger.info(f"✅ Instagram media ID: {media_id}")
        update_status(post_id, "posted", ig_media_id=media_id)
        send_message(
            chat_id,
            f"🎉 <b>Posted!</b>\n"
            f"Type: {post.post_type}\n"
            f"Instagram ID: {media_id}"
        )
        logger.info("✅ Post published successfully")
    except Exception as e:
        logger.error(f"❌ Instagram publish failed: {e}", exc_info=True)
        update_status(post_id, "failed")
        send_message(chat_id, f"❌ Publish failed: {str(e)}")
