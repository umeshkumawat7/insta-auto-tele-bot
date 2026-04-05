import os
import magic
import subprocess
from PIL import Image
from typing import List

def get_extension(path: str) -> str:
    return os.path.splitext(path)[1].lower().lstrip('.')

def is_image(path: str) -> bool:
    try:
        mime = magic.from_file(path, mime=True)
        return mime.startswith('image/')
    except:
        ext = get_extension(path)
        return ext in ['jpg', 'jpeg', 'png', 'webp']

def is_video(path: str) -> bool:
    try:
        mime = magic.from_file(path, mime=True)
        return mime.startswith('video/')
    except:
        ext = get_extension(path)
        return ext in ['mp4', 'mov', 'avi', 'mkv']

def get_video_duration(path: str) -> float:
    try:
        cmd = [
            'ffprobe', '-v', 'error', 
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except:
        pass
    return 0.0

def get_image_dimensions(path: str) -> tuple[int, int]:
    try:
        with Image.open(path) as img:
            return img.size
    except:
        return (0, 0)

def detect_post_type(file_paths: List[str], caption: str = "") -> str:
    caption_lower = caption.lower()
    
    if len(file_paths) > 1:
        return "CAROUSEL"
    
    if "story" in caption_lower:
        return "STORIES"
    if "reel" in caption_lower:
        return "REELS"
    if "video" in caption_lower and is_video(file_paths[0]):
        return "VIDEO"
    if "photo" in caption_lower or "image" in caption_lower:
        return "IMAGE"
    
    if is_image(file_paths[0]):
        return "IMAGE"
    if is_video(file_paths[0]):
        return "REELS"
    
    return "IMAGE"

def validate_for_instagram(path: str, post_type: str) -> None:
    if not os.path.exists(path):
        raise ValueError("File does not exist")
    
    file_size = os.path.getsize(path)
    ext = get_extension(path)
    
    if post_type == "IMAGE":
        try:
            mime = magic.from_file(path, mime=True)
            valid_format = mime in ['image/jpeg', 'image/png', 'image/webp']
        except:
            valid_format = ext in ['jpg', 'jpeg', 'png', 'webp']
            
        if not valid_format:
            raise ValueError("Image must be JPG, PNG, or WebP format")
        if file_size > 8 * 1024 * 1024:
            raise ValueError("Image must be smaller than 8 MB")
        width, height = get_image_dimensions(path)
        if min(width, height) < 320:
            raise ValueError("Image shortest side must be at least 320px")
    
    elif post_type in ["VIDEO", "REELS"]:
        try:
            mime = magic.from_file(path, mime=True)
            valid_format = mime in ('video/mp4', 'application/mp4', 'video/quicktime', 'video/x-m4v')
        except:
            valid_format = ext in ('mp4', 'mov', 'm4v')
            
        if not valid_format:
            raise ValueError("Video must be MP4 format")
        if file_size > 100 * 1024 * 1024:
            raise ValueError("Video must be smaller than 100 MB")
        duration = get_video_duration(path)
        if duration > 0:
            if post_type == "REELS" and duration > 90:
                raise ValueError("Reels must be 90 seconds or shorter")
            elif post_type == "VIDEO" and duration > 60:
                raise ValueError("Video must be 60 seconds or shorter")
    
    elif post_type == "STORIES":
        if is_image(path):
            try:
                mime = magic.from_file(path, mime=True)
                valid_format = mime in ['image/jpeg', 'image/png']
            except:
                valid_format = ext in ['jpg', 'jpeg', 'png']
                
            if not valid_format:
                raise ValueError("Story image must be JPG or PNG format")
            if file_size > 8 * 1024 * 1024:
                raise ValueError("Story image must be smaller than 8 MB")
        elif is_video(path):
            try:
                mime = magic.from_file(path, mime=True)
                valid_format = mime in ('video/mp4', 'application/mp4', 'video/quicktime', 'video/x-m4v')
            except:
                valid_format = ext in ('mp4', 'mov', 'm4v')
                
            if not valid_format:
                raise ValueError("Story video must be MP4 format")
            if file_size > 100 * 1024 * 1024:
                raise ValueError("Story video must be smaller than 100 MB")
            duration = get_video_duration(path)
            if duration > 0 and duration > 60:
                raise ValueError("Story video must be 60 seconds or shorter")
    
    elif post_type == "CAROUSEL":
        if is_image(path):
            try:
                mime = magic.from_file(path, mime=True)
                valid_format = mime in ['image/jpeg', 'image/png', 'image/webp']
            except:
                valid_format = ext in ['jpg', 'jpeg', 'png', 'webp']
                
            if not valid_format:
                raise ValueError("Carousel image must be JPG, PNG, or WebP format")
            if file_size > 8 * 1024 * 1024:
                raise ValueError("Carousel image must be smaller than 8 MB")
            width, height = get_image_dimensions(path)
            if min(width, height) < 320:
                raise ValueError("Carousel image shortest side must be at least 320px")
        elif is_video(path):
            try:
                mime = magic.from_file(path, mime=True)
                valid_format = mime in ('video/mp4', 'application/mp4', 'video/quicktime', 'video/x-m4v')
            except:
                valid_format = ext in ('mp4', 'mov', 'm4v')
                
            if not valid_format:
                raise ValueError("Carousel video must be MP4 format")
            if file_size > 100 * 1024 * 1024:
                raise ValueError("Carousel video must be smaller than 100 MB")
            duration = get_video_duration(path)
            if duration > 0 and duration > 60:
                raise ValueError("Carousel video must be 60 seconds or shorter")
