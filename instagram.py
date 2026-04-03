import os
import requests
import time
from typing import List

BASE = "https://graph.facebook.com/v25.0"
TOKEN = os.getenv("IG_ACCESS_TOKEN")
USER_ID = os.getenv("IG_USER_ID")

class TokenExpiredError(Exception):
    pass

class RateLimitError(Exception):
    pass

class APIError(Exception):
    pass

def _post(endpoint: str, params: dict) -> dict:
    params["access_token"] = TOKEN
    response = requests.post(BASE + endpoint, json=params)
    data = response.json()
    _handle_error(data)
    return data

def _get(endpoint: str, params: dict = None) -> dict:
    if params is None:
        params = {}
    params["access_token"] = TOKEN
    response = requests.get(BASE + endpoint, params=params)
    data = response.json()
    _handle_error(data)
    return data

def _handle_error(response: dict) -> None:
    if "error" in response:
        error = response["error"]
        code = error.get("code", 0)
        message = error.get("message", "Unknown error")
        
        if code == 190:
            raise TokenExpiredError(message)
        elif code in [4, 32]:
            raise RateLimitError(message)
        else:
            raise APIError(message)

def _create_container(params: dict) -> str:
    response = _post(f"/{USER_ID}/media", params)
    return response["id"]

def _poll_until_ready(container_id: str, max_wait: int = 120) -> None:
    for _ in range(max_wait // 5):
        try:
            response = _get(f"/{container_id}", {"fields": "status_code"})
            status = response.get("status_code")
            
            if status == "FINISHED":
                return
            elif status == "ERROR":
                raise APIError("Instagram processing failed")
            elif status == "EXPIRED":
                raise APIError("Instagram container expired")
            
            time.sleep(5)
        except Exception as e:
            if isinstance(e, APIError):
                raise
            time.sleep(5)
    
    raise TimeoutError("Container took too long to process")

def _publish_container(container_id: str) -> str:
    response = _post(f"/{USER_ID}/media_publish", {"creation_id": container_id})
    return response["id"]

def post_image(image_url: str, caption: str = "") -> str:
    container_id = _create_container({"image_url": image_url, "caption": caption})
    return _publish_container(container_id)

def post_reel(video_url: str, caption: str = "") -> str:
    container_id = _create_container({
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption
    })
    _poll_until_ready(container_id)
    return _publish_container(container_id)

def post_video(video_url: str, caption: str = "") -> str:
    container_id = _create_container({
        "media_type": "VIDEO",
        "video_url": video_url,
        "caption": caption
    })
    _poll_until_ready(container_id)
    return _publish_container(container_id)

def post_story(media_url: str, is_video: bool = False) -> str:
    if is_video:
        params = {"media_type": "STORIES", "video_url": media_url}
    else:
        params = {"media_type": "STORIES", "image_url": media_url}
    
    container_id = _create_container(params)
    if is_video:
        _poll_until_ready(container_id)
    return _publish_container(container_id)

def post_carousel(media_urls: List[str], caption: str = "") -> str:
    child_ids = []
    
    for url in media_urls:
        if url.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            child_id = _create_container({
                "image_url": url,
                "is_carousel_item": "true"
            })
        else:
            child_id = _create_container({
                "media_type": "VIDEO",
                "video_url": url,
                "is_carousel_item": "true"
            })
            _poll_until_ready(child_id)
        
        child_ids.append(child_id)
    
    carousel_id = _create_container({
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption
    })
    
    return _publish_container(carousel_id)

def publish(post_type: str, media_urls: List[str], caption: str = "") -> str:
    if post_type == "IMAGE":
        return post_image(media_urls[0], caption)
    elif post_type == "VIDEO":
        return post_video(media_urls[0], caption)
    elif post_type == "REELS":
        return post_reel(media_urls[0], caption)
    elif post_type == "STORIES":
        return post_story(media_urls[0], is_video=media_urls[0].endswith('.mp4'))
    elif post_type == "CAROUSEL":
        return post_carousel(media_urls, caption)
    else:
        raise ValueError(f"Unknown post type: {post_type}")
