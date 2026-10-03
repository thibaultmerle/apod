#!/usr/bin/env python3
"""
APOD Wallpaper Overlay
Automatically composites NASA APOD information overlay onto your desktop wallpaper.
"""

import argparse
from datetime import datetime, timedelta
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from PIL import Image
import requests

# Configuration
OUTPUT_DIR = os.path.expanduser("~/dev/apod/pic")
DATA_CACHE = os.path.join(OUTPUT_DIR, "apod_data.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Typography & Layout Configuration
FONT_FAMILY = "DejaVu-Sans"
SCREEN_TITLE_SIZE = 24
SCREEN_DATE_SIZE = 14
SCREEN_EXPLANATION_SIZE = 13
SCREEN_MARGIN = 25
SCREEN_BOTTOM_COPYRIGHT = 35
MAX_STORAGE_MB = 256
EARLIEST_APOD_DATE = datetime(1995, 6, 16).date()


def get_nasa_api_key():
    """Retrieve NASA API key from environment, config file, or default to DEMO_KEY."""
    if os.environ.get("NASA_API_KEY"):
        return os.environ["NASA_API_KEY"].strip()
    for path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_key.txt"),
        os.path.expanduser("~/.config/apod/api_key"),
    ]:
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    key = f.read().strip()
                    if key:
                        return key
            except Exception:
                pass
    return "DEMO_KEY"


NASA_API_KEY = get_nasa_api_key()


def get_screen_resolution():
    """Detect primary monitor or active display resolution using xrandr."""
    try:
        res = subprocess.run(["xrandr"], capture_output=True, text=True, check=True)
        # 1. Check for connected primary monitor mode
        primary_match = re.search(r"connected primary (\d+)x(\d+)", res.stdout)
        if primary_match:
            return int(primary_match.group(1)), int(primary_match.group(2))

        # 2. Check for active display mode (marked with '*')
        lines = res.stdout.splitlines()
        for line in lines:
            if "*" in line:
                m = re.search(r"(\d+)x(\d+)", line)
                if m:
                    return int(m.group(1)), int(m.group(2))

        # 3. Check for virtual screen current resolution
        m = re.search(r"current\s+(\d+)\s+x\s+(\d+)", res.stdout)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception as e:
        print(f"   Warning: Could not detect screen resolution: {e}")
    return None


def get_picture_options():
    """Get GNOME desktop background scaling option ('zoom', 'scaled', etc.)."""
    try:
        res = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.background", "picture-options"],
            capture_output=True, text=True, check=True
        )
        return res.stdout.strip().strip("'\"")
    except Exception:
        return "zoom"


def set_wallpaper(image_path):
    """Set the GNOME desktop background for both light and dark modes."""
    try:
        uri = f"file://{os.path.abspath(image_path)}"
        for key in ["picture-uri", "picture-uri-dark"]:
            subprocess.run(["gsettings", "set", "org.gnome.desktop.background", key, uri], check=True)
        print(f"   Wallpaper set to: {image_path}")
        return True
    except Exception as e:
        print(f"   Error setting wallpaper: {e}")
        return False


def enrich_apod_if_broken(data, query_date):
    """
    Workaround for NASA API backend bug returning the site logo placeholder
    or generic placeholder/canned metadata.
    Scrapes the actual high-res image, title, and explanation directly from science.nasa.gov.
    """
    is_broken_logo = "nasa-logo" in data.get("url", "")
    is_broken_title = data.get("title") == "NASA Science"
    is_canned_exp = "Curiosity Rover recorded this selfie" in data.get("explanation", "") and query_date != "2026-10-03"

    if not data or (not is_broken_logo and not is_broken_title and not is_canned_exp):
        return data

    print(f"   Detected placeholder/buggy metadata for {query_date}; resolving real article from web...")
    if is_canned_exp or is_broken_title:
        data["explanation"] = ""

    dt = datetime.strptime(query_date, "%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    article_url = None

    try:
        # 1. If today, find article link from main APOD page
        if query_date == today_str:
            r = requests.get("https://science.nasa.gov/apod/", timeout=10)
            if r.status_code == 200:
                art_m = re.search(r'href="(https://science\.nasa\.gov/image-article/apod-[^"]+)"', r.text)
                if art_m:
                    article_url = art_m.group(1).rstrip("/") + "/"
                else:
                    img_m = re.search(r'src="(https://assets\.science\.nasa\.gov/dynamicimage/assets/science/cds/apod/[^"]+)"', r.text)
                    title_m = re.search(r'<h2[^>]*class="[^"]*display-48[^"]*"[^>]*>([^<]+)</h2>', r.text)
                    if img_m and title_m:
                        data["url"] = data["hdurl"] = img_m.group(1).split("?")[0]
                        data["title"] = title_m.group(1).strip()
                        return data

        # 2. Check recent archive (covers last ~30 days)
        if not article_url:
            r_arch = requests.get("https://science.nasa.gov/apod/archive/", timeout=10)
            if r_arch.status_code == 200:
                pat = rf'https://science\.nasa\.gov/image-article/apod-{dt.year}-{dt.strftime("%B").lower()}-{dt.day}-[^\"]+/'
                match = re.search(pat, r_arch.text, re.IGNORECASE)
                if match:
                    article_url = match.group(0).rstrip("/") + "/"

        # 3. If not in recent archive, use classic APOD redirect (covers all dates back to 1995)
        if not article_url:
            classic_url = f"https://apod.nasa.gov/apod/ap{dt.strftime('%y%m%d')}.html"
            r_classic = requests.get(classic_url, timeout=10)
            if r_classic.status_code == 200 and "image-article" in r_classic.url:
                article_url = r_classic.url
            elif r_classic.status_code == 200 and "apod.nasa.gov" in r_classic.url:
                # Classic HTML fallback (true apod.nasa.gov page)
                img_m = re.search(r'<a\s+href="([^"]+\.(?:jpg|png|gif))"', r_classic.text, re.IGNORECASE)
                title_m = re.search(r'<title>APOD:\s*[^–-]+[–-]\s*([^<-]+)', r_classic.text)
                exp_m = re.search(r'<b>\s*Explanation:\s*</b>\s*(.*?)(?:<p>|<b>|</td>)', r_classic.text, re.DOTALL | re.IGNORECASE)
                if img_m:
                    img_path = img_m.group(1)
                    data["url"] = data["hdurl"] = img_path if img_path.startswith("http") else f"https://apod.nasa.gov/apod/{img_path}"
                if title_m:
                    data["title"] = html.unescape(title_m.group(1).strip())
                if exp_m:
                    data["explanation"] = " ".join(html.unescape(re.sub(r'<[^>]+>', '', exp_m.group(1))).split())
                if img_m:
                    return data

        # 4. If we resolved an image-article URL, parse it
        if article_url:
            print(f"   Found article: {article_url}")
            r_art = requests.get(article_url, timeout=10)
            if r_art.status_code == 200:
                img_m = re.search(r'src="(https://assets\.science\.nasa\.gov/(?:dynamicimage/assets|content/dam)/science/cds/apod/[^"]+)"', r_art.text)
                if not img_m:
                    img_m = re.search(r'property="og:image"\s+content="(https://assets\.science\.nasa\.gov/[^"]+)"', r_art.text)
                title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', r_art.text)
                if not title_m:
                    title_m = re.search(r'<title>APOD:\s*[^–-]+[–-]\s*([^<-]+)', r_art.text)

                exp_m = re.search(r'<(?:strong|b)>\s*Explanation:\s*</(?:strong|b)>\s*(.*?)(?:<br\s*/?>\s*<br\s*/?>\s*<(?:strong|b)>|</p>|</div>)', r_art.text, re.DOTALL | re.IGNORECASE)
                if not exp_m:
                    exp_m = re.search(r'Explanation:\s*</(?:strong|b)>\s*(.*?)(?:<br\s*/?>\s*<br\s*/?>\s*<(?:strong|b)>|</p>|</div>)', r_art.text, re.DOTALL | re.IGNORECASE)

                credit_m = re.search(r'<th[^>]*>\s*Credit\s*(?:&amp;|&)\s*Copyright\s*</th>\s*<td[^>]*>(.*?)</td>', r_art.text, re.DOTALL | re.IGNORECASE)

                if img_m:
                    clean_img = img_m.group(1).split("?")[0].replace("/jcr:content/renditions/cq5dam.web.1280.1280.jpeg", "")
                    data["url"] = data["hdurl"] = clean_img
                    print(f"   Discovered full image: {data['url']}")
                if title_m:
                    data["title"] = html.unescape(title_m.group(1).strip())
                    print(f"   Discovered title: {data['title']}")
                if exp_m:
                    clean_exp = html.unescape(re.sub(r'<[^>]+>', '', exp_m.group(1))).strip()
                    data["explanation"] = " ".join(clean_exp.split())
                    print(f"   Discovered explanation: {data['explanation'][:80]}...")
                if credit_m:
                    data["copyright"] = " ".join(html.unescape(re.sub(r'<[^>]+>', '', credit_m.group(1))).split())
    except Exception as e:
        print(f"   Could not scrape web page fallback: {e}")
    return data


def fetch_apod_data(target_date=None, fallback_to_cache=False, verbose=True):
    """Fetch APOD metadata from NASA API with local caching and fallbacks."""
    query_date = target_date or datetime.now().strftime("%Y-%m-%d")

    # Check local cache
    if os.path.exists(DATA_CACHE):
        try:
            with open(DATA_CACHE) as f:
                cached = json.load(f)
                is_canned = "Curiosity Rover recorded this selfie" in cached.get("explanation", "") and query_date != "2026-10-03"
                if cached.get("date") == query_date and "nasa-logo" not in cached.get("url", "") and cached.get("title") != "NASA Science" and not is_canned:
                    if verbose:
                        print(f"   Using cached APOD data for {query_date}")
                    return cached
        except Exception as e:
            if verbose:
                print(f"Error reading cache: {e}")

    api_key = get_nasa_api_key()
    url_base = f"https://api.nasa.gov/planetary/apod?api_key={api_key}&date={query_date}"
    max_retries = 2
    retry_delay = 3

    for attempt in range(max_retries):
        for try_thumbs in [True, False]:
            url = f"{url_base}&thumbs=True" if try_thumbs else url_base
            try:
                if verbose:
                    print(f"   Fetching fresh APOD data from NASA for {query_date} (Attempt {attempt + 1}/{max_retries})...")
                res = requests.get(url, timeout=12)

                # Timezone offset handling: if date not yet available, fallback to yesterday
                if res.status_code == 400 and not target_date:
                    if verbose:
                        print("   Target date not yet available at NASA (timezone offset), falling back to yesterday...")
                    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    return fetch_apod_data(yesterday, fallback_to_cache=fallback_to_cache, verbose=verbose)

                if res.status_code in (429, 500):
                    if verbose:
                        print(f"\n⚠️  NASA API returned HTTP {res.status_code} ({'Rate Limit' if res.status_code == 429 else 'Server Error'})")
                    if try_thumbs:
                        continue
                    if fallback_to_cache and os.path.exists(DATA_CACHE):
                        with open(DATA_CACHE) as f:
                            if verbose:
                                print("   Falling back to last known cached APOD data...")
                            return json.load(f)
                    return None

                res.raise_for_status()
                data = enrich_apod_if_broken(res.json(), query_date)

                if data and "nasa-logo" not in data.get("url", "") and data.get("title") != "NASA Science":
                    try:
                        with open(DATA_CACHE, "w") as f:
                            json.dump(data, f, indent=4)
                    except Exception as e:
                        if verbose:
                            print(f"Error saving cache: {e}")
                return data

            except requests.exceptions.RequestException as e:
                if not try_thumbs and verbose:
                    print(f"   Network/API error (attempt {attempt + 1}): {e}")

        if attempt < max_retries - 1:
            if verbose:
                print(f"   Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            retry_delay += 3

    if fallback_to_cache and os.path.exists(DATA_CACHE):
        try:
            with open(DATA_CACHE) as f:
                if verbose:
                    print("   Using last available cached data due to network failure.")
                return json.load(f)
        except Exception:
            pass
    return None


def resolve_media_url(apod_data):
    """Extract valid image or thumbnail URL, handling video sources."""
    if not apod_data:
        return None
    url = apod_data.get("hdurl") or apod_data.get("url")
    if apod_data.get("media_type") == "video":
        thumb = apod_data.get("thumbnail_url")
        vid_url = apod_data.get("url", "")
        if thumb and "nasa-logo" not in thumb:
            return thumb
        for pattern in [r"youtube\.com/embed/([^?&]+)", r"youtu\.be/([^?&]+)"]:
            m = re.search(pattern, vid_url)
            if m:
                return f"https://img.youtube.com/vi/{m.group(1)}/maxresdefault.jpg"
        if vid_url and any(vid_url.lower().endswith(ext) for ext in [".mp4", ".webm", ".ogg", ".mov", ".mkv"]):
            return vid_url
        return None
    if not url or "nasa-logo" in url:
        return None
    return url


def download_apod_image(image_url, date_str):
    """Download image or extract video frame, ensuring it is not a stale placeholder."""
    if not image_url:
        return None
    local_path = os.path.join(OUTPUT_DIR, f"apod_image_{date_str}.jpg")

    if os.path.exists(local_path):
        try:
            with Image.open(local_path) as img:
                if img.width >= 100 and img.height >= 100:
                    print(f"   Using cached APOD image: {local_path}")
                    return local_path
                print(f"   Cached image is a placeholder ({img.width}x{img.height}). Re-downloading...")
                os.remove(local_path)
        except Exception:
            try:
                os.remove(local_path)
            except Exception:
                pass

    if "nasa-logo" in image_url:
        print("   ERROR: Cannot download image (received NASA logo placeholder).")
        return None

    print(f"   Downloading APOD image from: {image_url}")
    # Extract frame if directly linking to a video file
    if any(image_url.lower().endswith(ext) for ext in [".mp4", ".webm", ".ogg", ".mov", ".mkv"]):
        try:
            subprocess.run(["ffmpeg", "-y", "-i", image_url, "-vframes", "1", "-q:v", "2", local_path],
                           check=True, capture_output=True)
            return local_path
        except Exception as e:
            print(f"Error extracting video frame: {e}")
            return None

    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(image_url, headers=headers, timeout=30)
        res.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(res.content)
        with Image.open(local_path) as img:
            img.verify()
        print(f"   Image saved to: {local_path}")
        return local_path
    except Exception as e:
        print(f"Error downloading image: {e}")
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
        return None


def create_overlay_image(apod_data, screen_size, side_bar_w=0, requested_date=None):
    """Render high-resolution text and gradient overlay at native screen resolution."""
    screen_w, screen_h = screen_size

    # Limit text paragraph width when side bars exist (e.g. square/portrait pictures in 'scaled' mode).
    # Otherwise, do not limit paragraph width (let it use the full available screen width).
    if side_bar_w >= 100:
        text_w = max(250, side_bar_w - SCREEN_MARGIN - 15)
    else:
        text_w = max(300, screen_w - 2 * SCREEN_MARGIN)

    def pango_escape(text):
        return html.escape(str(text or "")).replace("&amp;", "&amp;amp;")

    title = pango_escape(apod_data.get("title", "Astronomy Picture of the Day"))
    date_str = apod_data.get("date", "")
    if date_str:
        try:
            date_str = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
        except Exception:
            pass
    if requested_date and requested_date != apod_data.get("date"):
        date_str += f"  •  Closest available to {requested_date}"
    date_str = pango_escape(date_str)
    explanation = pango_escape(apod_data.get("explanation", ""))
    copyright_text = pango_escape(" ".join(apod_data.get("copyright", "").split()))

    full_block = (
        f'<span font="{FONT_FAMILY} Bold {SCREEN_TITLE_SIZE}" foreground="white">{title}</span>\n'
        f'<span font="{FONT_FAMILY} Bold {SCREEN_DATE_SIZE}" foreground="#c8dcff">{date_str}</span>\n\n'
        f'<span font="{FONT_FAMILY} {SCREEN_EXPLANATION_SIZE}" foreground="#e6e6e6">{explanation}</span>'
    )
    if copyright_text:
        full_block += f'\n\n<span font="{FONT_FAMILY} {SCREEN_DATE_SIZE}" foreground="#b4b4b4">{copyright_text}</span>'

    with tempfile.TemporaryDirectory() as tmpdir:
        overlay_path = os.path.join(tmpdir, "overlay.png")
        cmd = ["convert", "-size", f"{screen_w}x{screen_h}", "canvas:none"]

        # When overlaying on the picture (no side bars), add a gradient panel at the bottom for contrast
        if side_bar_w < 100:
            fade_h = int(screen_h * 0.22)
            solid_h = int(screen_h * 0.12)
            panel_y = screen_h - (fade_h + solid_h)
            cmd.extend([
                "(",
                    "(", "-size", f"{screen_w}x{fade_h}", "gradient:none-rgba(0,0,0,0.92)", ")",
                    "(", "-size", f"{screen_w}x{solid_h}", "xc:rgba(0,0,0,0.92)", ")",
                    "-append",
                ")",
                "-geometry", f"+0+{panel_y}", "-composite"
            ])
        else:
            # Side bar is already black, but a subtle vertical gradient ensures clean transition
            panel_height = int(screen_h * 0.45)
            panel_y = screen_h - panel_height
            cmd.extend([
                "(", "-size", f"{side_bar_w}x{panel_height}", "gradient:rgba(0,0,0,0.85)-none", "-rotate", "180", ")",
                "-geometry", f"+{screen_w - side_bar_w}+{panel_y}", "-composite"
            ])

        cmd.extend([
            "-background", "none", "-fill", "white", "-gravity", "SouthEast",
            "-define", "pango:align=right", "-size", f"{text_w}x",
            f"pango:{full_block}",
            "-geometry", f"+{SCREEN_MARGIN}+{SCREEN_BOTTOM_COPYRIGHT}", "-composite",
            overlay_path
        ])

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return Image.open(overlay_path).convert("RGBA")
        except subprocess.CalledProcessError as e:
            print(f"ImageMagick Error: {e.stderr.decode()}")
            return None


def composite_overlay_on_wallpaper(wallpaper_path, apod_data, output_path, requested_date=None):
    """Composite the generated overlay onto a native screen-resolution wallpaper canvas."""
    try:
        base_img = Image.open(wallpaper_path).convert("RGBA")
        img_w, img_h = base_img.size

        screen_res = get_screen_resolution()
        if not screen_res:
            print("   Warning: Could not detect display resolution; defaulting to 1920x1080.")
            screen_res = (1920, 1080)

        screen_w, screen_h = screen_res
        mode = get_picture_options()

        # 1. Create native screen-resolution canvas
        canvas = Image.new("RGBA", (screen_w, screen_h), (0, 0, 0, 255))
        side_bar_w = 0

        # 2. Scale and position the base APOD image onto the canvas
        if mode == "scaled":
            scale = min(screen_w / img_w, screen_h / img_h)
            new_w, new_h = max(1, int(img_w * scale)), max(1, int(img_h * scale))
            scaled_img = base_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            paste_x = (screen_w - new_w) // 2
            paste_y = (screen_h - new_h) // 2
            canvas.paste(scaled_img, (paste_x, paste_y))
            right_bar = screen_w - (paste_x + new_w)
            if right_bar >= 100:
                side_bar_w = right_bar
        elif mode == "centered":
            paste_x = (screen_w - img_w) // 2
            paste_y = (screen_h - img_h) // 2
            canvas.paste(base_img, (paste_x, paste_y))
            right_bar = screen_w - (paste_x + img_w)
            if right_bar >= 100:
                side_bar_w = right_bar
        elif mode == "stretched":
            scaled_img = base_img.resize((screen_w, screen_h), Image.Resampling.LANCZOS)
            canvas.paste(scaled_img, (0, 0))
        else:  # 'zoom', 'spanned', or default
            scale = max(screen_w / img_w, screen_h / img_h)
            new_w, new_h = max(1, int(img_w * scale)), max(1, int(img_h * scale))
            scaled_img = base_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            crop_x = (new_w - screen_w) // 2
            crop_y = (new_h - screen_h) // 2
            canvas.paste(scaled_img.crop((crop_x, crop_y, crop_x + screen_w, crop_y + screen_h)), (0, 0))

        # 3. Create native screen-resolution overlay
        overlay = create_overlay_image(apod_data, (screen_w, screen_h), side_bar_w=side_bar_w, requested_date=requested_date)
        if not overlay:
            return False

        # 4. Alpha composite onto screen canvas
        composited = Image.alpha_composite(canvas, overlay)
        if output_path.lower().endswith((".jpg", ".jpeg")):
            composited.convert("RGB").save(output_path, "JPEG", quality=95)
        else:
            composited.save(output_path, "PNG")

        file_size = os.path.getsize(output_path)
        size_str = f"{file_size / (1024 * 1024):.2f} MB" if file_size >= 1024 * 1024 else f"{file_size / 1024:.1f} KB"
        print(f"   Desktop Scaling Mode: {mode} on {screen_w}x{screen_h}")
        print(f"   Composited Dimensions: {screen_w}x{screen_h} ({size_str})")
        print(f"   Composited image saved to: {output_path}")
        return True
    except Exception as e:
        print(f"Error compositing overlay: {e}")
        return False


def cleanup_directory(directory, max_size_mb):
    """Purge raw images and oldest wallpapers if total size exceeds max_size_mb quota."""
    print(f"\n5. Cleaning up directory: {directory}")

    # 1. Always purge any lingering raw images (keep only final composited wallpapers)
    for f in os.listdir(directory):
        if f.startswith("apod_image_") and f.endswith(".jpg"):
            try:
                os.remove(os.path.join(directory, f))
            except Exception:
                pass

    max_bytes = max_size_mb * 1024 * 1024
    try:
        files = []
        for f in os.listdir(directory):
            if f.endswith(".json") or f == "example.jpg":
                continue
            p = os.path.join(directory, f)
            if os.path.isfile(p):
                files.append((p, os.path.getsize(p), os.path.getmtime(p)))

        total_size = sum(sz for _, sz, _ in files)
        print(f"   Current size: {total_size / (1024 * 1024):.2f} MB (Limit: {max_size_mb} MB)")
        if total_size <= max_bytes:
            print("   Size is within limits. No cleanup needed.")
            return

        # Sort by mtime (oldest first), keeping at least the latest file
        files.sort(key=lambda x: x[2])
        to_delete = files[:-1] if len(files) > 1 else []
        deleted = reclaimed = 0

        for path, size, _ in to_delete:
            if total_size <= max_bytes:
                break
            try:
                os.remove(path)
                total_size -= size
                reclaimed += size
                deleted += 1
                print(f"   Deleted: {os.path.basename(path)}")
            except OSError as e:
                print(f"   Error deleting {os.path.basename(path)}: {e}")

        print(f"   Cleanup complete. Deleted {deleted} files, reclaimed {reclaimed / (1024 * 1024):.2f} MB.")
    except Exception as e:
        print(f"Error during cleanup: {e}")


def try_get_apod(date_str, verbose=True):
    """
    Attempt to fetch APOD metadata and download the image for a given date.
    Returns (apod_data, wallpaper_path) if successful, or (None, None) if unavailable.
    """
    data = fetch_apod_data(date_str, fallback_to_cache=(date_str is None), verbose=verbose)
    if not data:
        return None, None
    image_url = resolve_media_url(data)
    if not image_url:
        return None, None
    wallpaper_path = download_apod_image(image_url, data.get("date"))
    if not wallpaper_path or not os.path.exists(wallpaper_path):
        return None, None
    return data, wallpaper_path


def get_closest_apod_with_picture(target_date_str=None):
    """
    Retrieve APOD data and image for target_date_str.
    If no valid picture is available for that day, search for and return
    the closest day that has a valid picture.
    Returns (apod_data, wallpaper_path, signed_offset).
    """
    today = datetime.now().date()

    if target_date_str:
        try:
            req_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            req_date = today
    else:
        req_date = today
        target_date_str = req_date.strftime("%Y-%m-%d")

    # If requested date is before first APOD or in future, notify immediately
    if req_date < EARLIEST_APOD_DATE:
        print(f"\n⚠️  Requested date {target_date_str} is before the first APOD ({EARLIEST_APOD_DATE.strftime('%Y-%m-%d')}).")
        print(f"   Selecting the earliest available APOD ({EARLIEST_APOD_DATE.strftime('%Y-%m-%d')})...")
        req_date = EARLIEST_APOD_DATE
        effective_target = req_date.strftime("%Y-%m-%d")
        data, path = try_get_apod(effective_target, verbose=True)
        if data and path:
            return data, path, (req_date - datetime.strptime(target_date_str, "%Y-%m-%d").date()).days
    elif req_date > today:
        print(f"\n⚠️  Requested date {target_date_str} is in the future.")
        print(f"   Searching backwards from today ({today.strftime('%Y-%m-%d')})...")
        req_date = today

    # 1. Try requested date first
    current_date_str = req_date.strftime("%Y-%m-%d")
    data, path = try_get_apod(current_date_str, verbose=True)
    if data and path:
        return data, path, 0

    # 2. If no picture available for requested date, search for closest day
    print(f"\n⚠️  No valid picture available for {target_date_str}.")
    print("   Searching for the closest day with an available picture...")

    max_search_days = 60
    for offset in range(1, max_search_days + 1):
        candidates = []
        # Candidate 1: future (+offset days) if <= today
        cand_future = req_date + timedelta(days=offset)
        if cand_future <= today:
            candidates.append((cand_future, offset))
        # Candidate 2: past (-offset days) if >= EARLIEST_APOD_DATE
        cand_past = req_date - timedelta(days=offset)
        if cand_past >= EARLIEST_APOD_DATE:
            candidates.append((cand_past, -offset))

        # Prioritize locally cached wallpaper files at this distance
        candidates.sort(
            key=lambda item: not os.path.exists(
                os.path.join(OUTPUT_DIR, f"apod_wallpaper_{item[0].strftime('%Y-%m-%d')}.png")
            )
        )

        for cand_dt, cand_offset in candidates:
            cand_str = cand_dt.strftime("%Y-%m-%d")
            c_data, c_path = try_get_apod(cand_str, verbose=False)
            if c_data and c_path:
                days_diff = abs(cand_offset)
                direction = "later" if cand_offset > 0 else "earlier"
                days_word = f"{days_diff} day{'s' if days_diff > 1 else ''}"
                print("\n" + "=" * 60)
                print(f"👉 NO IMAGE AVAILABLE FOR {target_date_str}!")
                print(f"   TAKING THE CLOSER AVAILABLE ONE: {cand_str} ({days_word} {direction})")
                print("=" * 60 + "\n")
                return c_data, c_path, cand_offset

    return None, None, 0


def main():
    parser = argparse.ArgumentParser(description="APOD Wallpaper Overlay")
    parser.add_argument("date", nargs="?", help="Date in YYYYMMDD format")
    args = parser.parse_args()

    target_date_str = None
    if args.date:
        try:
            target_date_str = datetime.strptime(args.date, "%Y%m%d").strftime("%Y-%m-%d")
            print(f"   Target date: {target_date_str}")
        except ValueError:
            print("ERROR: Date must be in YYYYMMDD format")
            sys.exit(1)

    print("=" * 60)
    print("APOD Wallpaper Overlay - Automatic Application")
    print("=" * 60)

    print("\n2. Fetching APOD data from NASA...")
    apod_data, wallpaper_path, offset = get_closest_apod_with_picture(target_date_str)
    if not apod_data or not wallpaper_path:
        print("ERROR: Failed to retrieve an APOD picture or its fallback.")
        sys.exit(1)

    print(f"   Base Image: {wallpaper_path}")
    try:
        with Image.open(wallpaper_path) as img:
            img_w, img_h = img.size
        file_size = os.path.getsize(wallpaper_path)
        size_str = f"{file_size / (1024 * 1024):.2f} MB" if file_size >= 1024 * 1024 else f"{file_size / 1024:.1f} KB"
        print(f"   Dimensions: {img_w}x{img_h} ({size_str})")
    except Exception:
        pass

    print(f"   Title: {apod_data.get('title', 'N/A')}")
    if target_date_str and target_date_str != apod_data.get("date"):
        print(f"   Date: {apod_data.get('date')} (Closest available to requested {target_date_str})")
    else:
        print(f"   Date: {apod_data.get('date', 'N/A')}")

    apod_date = apod_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    composited_output = os.path.join(OUTPUT_DIR, f"apod_wallpaper_{apod_date}.png")

    print("\n3. Creating overlay and compositing...")
    if not composite_overlay_on_wallpaper(wallpaper_path, apod_data, composited_output, requested_date=target_date_str):
        print("ERROR: Failed to create composited image")
        sys.exit(1)

    # Automatically remove intermediate raw image to conserve storage (keep only final wallpaper)
    if wallpaper_path and os.path.exists(wallpaper_path) and os.path.basename(wallpaper_path).startswith("apod_image_"):
        try:
            os.remove(wallpaper_path)
            print(f"   Removed intermediate raw image: {os.path.basename(wallpaper_path)}")
        except Exception:
            pass

    print("\n4. Setting new wallpaper...")
    if set_wallpaper(composited_output):
        cleanup_directory(OUTPUT_DIR, MAX_STORAGE_MB)
        print("\n" + "=" * 60)
        if target_date_str and target_date_str != apod_data.get("date"):
            print(f"SUCCESS! Wallpaper applied using closest available picture ({apod_data.get('date')})!")
            print(f"         (Requested {target_date_str} had no picture)")
        else:
            print("SUCCESS! Wallpaper with APOD overlay applied!")
        print("=" * 60)
    else:
        print("\nERROR: Failed to set wallpaper")
        sys.exit(1)


if __name__ == "__main__":
    main()
