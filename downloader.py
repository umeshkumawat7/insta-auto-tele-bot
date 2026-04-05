import requests
import os
import time
import re
import cloudinary
import cloudinary.uploader
from typing import List, Dict
from bot import get_file_url

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def upload_to_cloudinary(file_path: str) -> str:
    """Upload local file to Cloudinary and return public URL"""
    try:
        response = cloudinary.uploader.upload(
            file_path,
            resource_type="auto",  # Auto-detect image/video
            folder="instagram_posts"
        )
        return response["secure_url"]
    except Exception as e:
        raise Exception(f"Cloudinary upload failed: {str(e)}")

def download_from_url(url: str, dest_dir: str = "downloads") -> str:
    os.makedirs(dest_dir, exist_ok=True)
    
    if "instagram.com" in url or "youtube.com" in url or "youtu.be" in url or "tiktok.com" in url:
        try:
            import yt_dlp
            
            # Options to get the best video and save it to the dest_dir
            cookies_path = os.getenv("INSTAGRAM_COOKIES_FILE", "cookies.txt")

            ydl_opts = {
                'outtmpl': os.path.join(dest_dir, '%(id)s.%(ext)s'),
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                'quiet': True,
                'no_warnings': True,
                'http_headers': {
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'
                    ),
                },
            }

            if os.path.exists(cookies_path):
                ydl_opts['cookiefile'] = cookies_path
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                base = os.path.splitext(downloaded_file)[0]
                for ext in ['.mp4', '.mkv', '.webm', '.mov']:
                    candidate = base + ext
                    if os.path.exists(candidate):
                        return candidate
                return downloaded_file
        except Exception as e:
            raise Exception(f"yt-dlp download failed: {str(e)}")
            
    # Fallback to requests for direct file URLs
    for attempt in range(3):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '')
            content_disposition = response.headers.get('content-disposition', '')
            
            if 'filename=' in content_disposition:
                filename = re.search(r'filename="?([^"]+)"?', content_disposition).group(1)
            else:
                import urllib.parse
                import mimetypes
                
                parsed_url = urllib.parse.urlparse(url)
                path = urllib.parse.unquote(parsed_url.path).rstrip('/')
                filename = os.path.basename(path)
                if not filename:
                    filename = f"download_{int(time.time())}"
                
                # If filename has no extension, try to guess from Content-Type header
                if '.' not in filename and content_type:
                    mime = content_type.split(';')[0].strip()
                    ext = mimetypes.guess_extension(mime)
                    if ext:
                        filename += ext
            
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            filepath = os.path.join(dest_dir, filename)
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return filepath
            
        except Exception as e:
            if attempt == 2:
                raise e
            time.sleep(2 ** attempt)
    
    raise Exception("Download failed after 3 attempts")

def download_from_telegram(file_id: str, dest_dir: str = "downloads") -> str:
    file_url = get_file_url(file_id)
    if not file_url:
        raise Exception("Could not get Telegram file URL")
    return download_from_url(file_url, dest_dir)

def download_all(sources: List[Dict], dest_dir: str = "downloads") -> List[str]:
    paths = []
    for source in sources:
        if source["type"] == "url":
            path = download_from_url(source["value"], dest_dir)
        elif source["type"] == "file_id":
            path = download_from_telegram(source["value"], dest_dir)
        else:
            continue
        paths.append(path)
    return paths

def download_and_upload_all(sources: List[Dict], dest_dir: str = "downloads") -> List[str]:
    """Download files and upload to Cloudinary, return Cloudinary URLs"""
    local_paths = download_all(sources, dest_dir)
    cloudinary_urls = []
    
    for local_path in local_paths:
        try:
            cloudinary_url = upload_to_cloudinary(local_path)
            cloudinary_urls.append(cloudinary_url)
            # Clean up local file after upload
            os.remove(local_path)
        except Exception as e:
            # Clean up on failure too
            if os.path.exists(local_path):
                os.remove(local_path)
            raise e
    
    return cloudinary_urls

def get_public_url(filename: str) -> str:
    """Legacy function - now returns Cloudinary URL"""
    # This function is kept for compatibility but should use upload_to_cloudinary
    return ""
