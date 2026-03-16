#!/usr/bin/env python3
"""
APOD Wallpaper Overlay
Automatically composites APOD information overlay onto the current wallpaper
"""

import requests
import json
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os
import sys
import time
import subprocess
import urllib.parse
import tempfile
import argparse
import html

# NASA API key (you can get one from https://api.nasa.gov/)
NASA_API_KEY = "DEMO_KEY"

# Configuration
OUTPUT_DIR = os.path.expanduser("~/dev/apod/pic")
DATA_CACHE = os.path.join(OUTPUT_DIR, "apod_data.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Rendering Configuration
FONT_FAMILY = "DejaVu-Sans"
SCREEN_TITLE_SIZE = 20       # Desired size in screen pixels
SCREEN_DATE_SIZE = 12        # Desired size in screen pixels
SCREEN_EXPLANATION_SIZE = 12 # Desired size in screen pixels
RESOLUTION_SCALE = 8 # High quality super-sampling. Values > 8 may exhaust ImageMagick memory.
MAX_STORAGE_MB = 256 # Limit for the pic directory
UPDATE_FREQUENCY_HOURS = 4 # Reference value for systemd timer

# Margins are now SCREEN RELATIVE (in screen pixels) to ensure consistent look
# regardless of underlying image resolution or scaling.
SCREEN_MARGIN = 15
SCREEN_BOTTOM_COPYRIGHT = 30 # Distance from screen bottom
SCREEN_BOTTOM_TEXT = 45      # Distance from screen bottom

# Fallback margins for when screen resolution isn't detected (image pixels)
FALLBACK_MARGIN = 15
FALLBACK_BOTTOM_COPYRIGHT = 80
FALLBACK_BOTTOM_TEXT = 100

PANEL_OPACITY = 0.92 

def get_screen_resolution():
    """Get the primary screen resolution using xrandr"""
    try:
        # Run xrandr to get screen info
        result = subprocess.run(['xrandr'], capture_output=True, text=True)
        
        # Look for the primary screen (marked with *)
        for line in result.stdout.splitlines():
            if '*' in line:
                # Line format example: "   2560x1440     60.00*+"
                parts = line.split()
                res_part = parts[0] # "2560x1440"
                if 'x' in res_part:
                    w, h = map(int, res_part.split('x'))
                    return w, h
                    
        # Fallback: try to find any resolution if no star found
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) > 0 and 'x' in parts[0]:
                try:
                    w, h = map(int, parts[0].split('x'))
                    return w, h
                except: continue
                
        return None
    except Exception as e:
        print(f"Error checking screen resolution: {e}")
        return None 

def get_current_wallpaper():
    """Get the current wallpaper path from GNOME settings"""
    try:
        result = subprocess.run(
            ['gsettings', 'get', 'org.gnome.desktop.background', 'picture-uri'],
            capture_output=True,
            text=True,
            check=True
        )
        wallpaper_uri = result.stdout.strip().strip("'\"")
        wallpaper_path = urllib.parse.unquote(wallpaper_uri.replace('file://', ''))
        
        # If the current wallpaper is already an apod overlay, find the original image
        if "dev/apod/pic" in wallpaper_path or not os.path.exists(wallpaper_path):
            cache_dir = os.path.expanduser("~/.cache/randomwallpaper@iflow.space/wallpapers/")
            if os.path.exists(cache_dir):
                # Find the most recently modified file that isn't an apod overlay
                files = [os.path.join(cache_dir, f) for f in os.listdir(cache_dir) 
                        if os.path.isfile(os.path.join(cache_dir, f))]
                if files:
                    # Sort by modification time
                    files.sort(key=os.path.getmtime, reverse=True)
                    return files[0]
        
        return wallpaper_path
    except Exception as e:
        print(f"Error resolving wallpaper path: {e}")
        return None

def get_picture_options():
    """Get the current wallpaper scaling option (zoom, scaled, etc.)"""
    try:
        result = subprocess.run(
            ['gsettings', 'get', 'org.gnome.desktop.background', 'picture-options'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip().strip("'\"")
    except Exception as e:
        print(f"Error getting picture options: {e}")
        return 'zoom' # Default fallback

def set_wallpaper(image_path):
    """Set the GNOME wallpaper"""
    try:
        file_uri = f"file://{image_path}"
        subprocess.run(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri', file_uri], check=True)
        subprocess.run(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri-dark', file_uri], check=True)
        print(f"Wallpaper set to: {image_path}")
        return True
    except Exception as e:
        print(f"Error setting wallpaper: {e}")
        return False

def fetch_apod_data(target_date=None):
    """Fetch APOD data from NASA API with local caching"""
    if target_date:
        query_date = target_date
    else:
        query_date = datetime.now().strftime('%Y-%m-%d')
    
    # Check if we have a valid cache for the target date
    if os.path.exists(DATA_CACHE):
        try:
            with open(DATA_CACHE, 'r') as f:
                cached_data = json.load(f)
                if cached_data.get('date') == query_date:
                    print(f"   Using cached APOD data for {query_date}")
                    return cached_data
        except Exception as e:
            print(f"Error reading cache: {e}")

    # If no cache or cache is old, fetch from NASA
    url = f"https://api.nasa.gov/planetary/apod?api_key={NASA_API_KEY}&thumbs=True"
    if target_date:
        url += f"&date={target_date}"
    
    max_retries = 5
    retry_delay = 10 # seconds
    
    for attempt in range(max_retries):
        try:
            print(f"   Fetching fresh APOD data from NASA (Attempt {attempt + 1}/{max_retries})...")
            response = requests.get(url, timeout=15)
            
            if response.status_code == 429:
                print("\n❌ NASA API Rate Limit Exceeded (429 Error)")
                print("   The 'DEMO_KEY' is very limited. Please get your own free API key")
                print("   at https://api.nasa.gov/ and update NASA_API_KEY in the script.")
                
                # If we have any cached data at all, use it as a fallback even if old
                if os.path.exists(DATA_CACHE):
                    with open(DATA_CACHE, 'r') as f:
                        print("   Falling back to last known cached data...")
                        return json.load(f)
                return None
                
            response.raise_for_status()
            data = response.json()
            
            # Save to cache
            try:
                with open(DATA_CACHE, 'w') as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                print(f"Error saving cache: {e}")
                
            return data
            
        except (requests.exceptions.RequestException, requests.exceptions.ConnectionError) as e:
            print(f"   Network error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                # Linear backoff
                retry_delay += 10
            else:
                print("   Max retries reached.")

    # Try to return old cache as ultimate fallback
    if os.path.exists(DATA_CACHE):
        try:
            with open(DATA_CACHE, 'r') as f:
                print("   Using last available cached data due to network failure.")
                return json.load(f)
        except: pass
    return None

def download_apod_image(image_url, date_str):
    """Download the APOD image if not already cached"""
    filename = f"apod_image_{date_str}.jpg"
    local_path = os.path.join(OUTPUT_DIR, filename)
    
    if os.path.exists(local_path):
        print(f"   Using cached APOD image: {local_path}")
        return local_path
        
    print(f"   Downloading APOD image from: {image_url}")
    
    # Check if URL directly points to a video file
    is_video_url = any(image_url.lower().endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.mov', '.mkv'])
    if is_video_url:
        print(f"   Extracting first frame from video...")
        try:
            cmd = ['ffmpeg', '-y', '-i', image_url, '-vframes', '1', '-q:v', '2', local_path]
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"   Video frame saved to: {local_path}")
            return local_path
        except Exception as e:
            print(f"Error extracting video frame: {e}")
            return None

    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        with open(local_path, 'wb') as f:
            f.write(response.content)
            
        print(f"   Image saved to: {local_path}")
        return local_path
    except Exception as e:
        print(f"Error downloading image: {e}")
        return None

def create_overlay_image(apod_data, base_image_size):
    """Create a professional high-quality overlay using ImageMagick's Pango engine and super-sampling"""
    width, height = base_image_size
    
    # Calculate dynamic resolution scale to prevent memory exhaustion
    MAX_DIMENSION = 10000
    max_side = max(width, height)
    resolution_scale = RESOLUTION_SCALE # Start with default preference
    
    if max_side * resolution_scale > MAX_DIMENSION:
        resolution_scale = MAX_DIMENSION / max_side
        print(f"   Image too large for full supersampling. Reducing scale to {resolution_scale:.2f}x (Max dim: {MAX_DIMENSION})")
    
    # Ensure we don't scale down below 1.0 for the workspace
    resolution_scale = max(1.0, resolution_scale)

    # Internal high-res dimensions
    sw = int(width * resolution_scale)
    sh = int(height * resolution_scale)
    
    # Calculate adaptive positioning based on screen resolution
    screen_res = get_screen_resolution()
    
    # Initialize default margins based on Image Pixels (fallback)
    margin_right_img = FALLBACK_MARGIN
    margin_bottom_copyright_img = FALLBACK_BOTTOM_COPYRIGHT
    margin_bottom_text_img = FALLBACK_BOTTOM_TEXT
    
    # Adaptive adjustment vars
    extra_bottom_visible = 0
    extra_right_visible = 0
    
    scale = 1.0 # Default scale
    
    if screen_res:
        screen_w, screen_h = screen_res
        
        # Get GNOME scaling mode
        scaling_mode = get_picture_options()
        print(f"   Desktop Scaling Mode: {scaling_mode}")
        
        # Default to 'zoom' behavior (Cover) if unknown
        # Zoom: Scale = max(w_ratio, h_ratio). Cropping occurs.
        # Scaled: Scale = min(w_ratio, h_ratio). No cropping (black bars).
        
        scale_w = screen_w / width
        scale_h = screen_h / height
        
        if scaling_mode == 'scaled':
             # Fit to screen (letterbox/pillarbox)
             scale = min(scale_w, scale_h)
             # In 'scaled' mode, the image is fully visible. No crop.
             extra_right_visible = 0
             extra_bottom_visible = 0
             
             # Note: If the image is pillarboxed (black bars on sides), the bottom of image == bottom of screen.
             # If letterboxed (black bars top/bottom), the bottom of image < bottom of screen.
             # But 'scaled' usually maximizes to touch at least one pair of edges.
             
        elif scaling_mode == 'spanned':
             # Spans multiple monitors? Treat as 1:1 map to screen rect
             scale = max(scale_w, scale_h) # Approx same as zoom for single screen logic
             extra_right_visible = max(0, ((width * scale) - screen_w) / 2 / scale)
             extra_bottom_visible = max(0, ((height * scale) - screen_h) / 2 / scale)
             
        else: 
            # 'zoom' (default), 'wallpaper', 'centered', 'none'
            # We assume 'zoom' behavior for calculations as it's the standard filling mode
            scale = max(scale_w, scale_h)
            
            # Dimensions of the visible part of the image in image pixels
            visible_w = screen_w / scale
            visible_h = screen_h / scale
            
            # Calculate how much is cropped (assuming center crop)
            total_crop_w = width - visible_w
            total_crop_h = height - visible_h
            
            extra_right_visible = max(0, total_crop_w / 2)
            extra_bottom_visible = max(0, total_crop_h / 2)
        
        # Now update the BASE margins to be screen-relative
        # We want SCREEN_MARGIN pixels from the edge of the SCREEN.
        # Convert screen pixels to image pixels: screen_px / scale
        
        margin_right_img = SCREEN_MARGIN / scale
        margin_bottom_copyright_img = SCREEN_BOTTOM_COPYRIGHT / scale
        margin_bottom_text_img = SCREEN_BOTTOM_TEXT / scale
        
        print(f"   Adapting overlay for screen {screen_w}x{screen_h}")
        print(f"   Image: {width}x{height}")
        print(f"   Scale: {scale:.4f}")
        print(f"   Margins (img px): Right={int(margin_right_img)}, BottomText={int(margin_bottom_text_img)}")
        print(f"   Crop Offset: Right={int(extra_right_visible)}, Bottom={int(extra_bottom_visible)}")
    
    else:
        print("   WARNING: Could not detect screen resolution. Using default fallback margins.")

        # Combine visible crop/shift with the desired visual margin
    final_margin_right_img = margin_right_img + extra_right_visible
    # We only use one bottom margin now, for the whole block.
    # We'll use the copyright margin as the base since it's the bottom-most element.
    final_margin_bottom_img = margin_bottom_copyright_img + extra_bottom_visible

    # Scale everything up for high-res rendering
    # Font sizes are now adaptive: Desired Screen Size / Image Scale = Required Image Size
    # Then multiplied by resolution_scale for the super-sampled canvas.
    st_size = (SCREEN_TITLE_SIZE / scale) * resolution_scale
    sd_size = (SCREEN_DATE_SIZE / scale) * resolution_scale
    se_size = (SCREEN_EXPLANATION_SIZE / scale) * resolution_scale
    
    s_margin_right = final_margin_right_img * resolution_scale
    s_margin_bottom = final_margin_bottom_img * resolution_scale
    
    # Prepare text data (escaping for Pango)
    def pango_escape(text):
        if not text:
            return ""
        # IMPORTANT: ImageMagick 6's Pango coder un-escapes once before passing to Pango.
        # This requires DOUBLE escaping for ampersands (& -> &amp;amp;).
        # html.escape handles &, <, >, ", ' (converts & to &amp;)
        escaped = html.escape(str(text))
        # Now convert &amp; to &amp;amp; to handle IM6's double un-escaping
        return escaped.replace('&amp;', '&amp;amp;')

    title = pango_escape(apod_data.get('title', 'Astronomy Picture of the Day'))
    date_str = apod_data.get('date', '')
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_str = date_obj.strftime('%B %d, %Y')
        except: pass
    date_str = pango_escape(date_str)
    explanation = pango_escape(apod_data.get('explanation', ''))
    
    raw_copyright = apod_data.get('copyright', '')
    # Remove newlines and excess whitespace from copyright to force single line
    if raw_copyright:
        raw_copyright = ' '.join(raw_copyright.split())
    copyright_text = pango_escape(raw_copyright)
    
    # We'll create the overlay using ImageMagick
    with tempfile.TemporaryDirectory() as tmpdir:
        overlay_path = os.path.join(tmpdir, "overlay.png")
        pango_markup_path = os.path.join(tmpdir, "markup.pango")
        
        # 1. Create the high-res text container width
        # We determine the max width of the text block.
        # It MUST NOT exceed the image width (sw) or it will be cropped.
        visual_margin_hr = (SCREEN_MARGIN / scale) * resolution_scale
        
        if screen_res:
             # Width of the visible image area in high-res pixels
             s_visible_w = (screen_res[0] / scale) * resolution_scale
             # We want a visual margin on BOTH sides of the text block
             text_w = s_visible_w - (2 * visual_margin_hr)
        else:
             # Fallback
             text_w = sw - (2 * visual_margin_hr)
        
        # CRITICAL FIX: The text block must fit inside the image dimensions (sw)
        # Even if screen_res is large, the canvas is limited to sw.
        text_w = min(text_w, sw - (2 * visual_margin_hr))
        
        # Ensure integer for ImageMagick command line
        text_w = int(text_w)
        st_size = int(st_size)
        sd_size = int(sd_size)
        se_size = int(se_size)
        s_margin_right = int(s_margin_right)
        s_margin_bottom = int(s_margin_bottom)
        
        # 1. Create the dark gradient panel
        panel_height = int(sh * 0.75) 
        panel_y = sh - panel_height
        
        # 2. Render everything in one go with ImageMagick at high res
        # We build a final command that passes the markup as a direct string.
        # ImageMagick 6 on some systems blocks the 'pango:@file' syntax.
        
        # Construct the single text block
        # Using double quotes for attributes (escaped if needed)
        full_block = f"<span font=\"{FONT_FAMILY} Bold {st_size}\" foreground=\"white\">{title}</span>\n"
        full_block += f"<span font=\"{FONT_FAMILY} Bold {sd_size}\" foreground=\"#c8dcff\">{date_str}</span>\n\n"
        full_block += f"<span font=\"{FONT_FAMILY} {se_size}\" foreground=\"#dddddd\">{explanation}</span>"
        
        if copyright_text:
            full_block += f"\n\n<span font=\"{FONT_FAMILY} {sd_size}\" foreground=\"#b4b4b4\">{copyright_text}</span>"
            
        cmd = [
            'convert',
            '-size', f'{sw}x{sh}', 'canvas:none',
            # Draw gradient panel
            '(', '-size', f'{sw}x{panel_height}', 'gradient:black-none', '-rotate', '180', ')',
            '-geometry', f'+0+{panel_y}', '-composite',
            # Render the main text block
            '-background', 'none',
            '-fill', 'white',
            '-gravity', 'SouthEast',
            '-define', 'pango:align=right',
            '-size', f'{text_w}x',
            f'pango:{full_block}',
            '-geometry', f'+{s_margin_right}+{s_margin_bottom}', '-composite',
            # Final Step: Resize down to original resolution
            '-resize', f'{width}x{height}',
            overlay_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return Image.open(overlay_path).convert('RGBA')
        except subprocess.CalledProcessError as e:
            print(f"ImageMagick Error: {e.stderr.decode()}")
            return None

def wrap_text(text, width):
    """Not needed as ImageMagick Pango handles wrapping"""
    return [text]

def composite_overlay_on_wallpaper(wallpaper_path, apod_data, output_path):
    """Composite the APOD overlay onto the wallpaper"""
    try:
        # Open the wallpaper
        wallpaper = Image.open(wallpaper_path)
        
        # Convert to RGBA if needed
        if wallpaper.mode != 'RGBA':
            wallpaper = wallpaper.convert('RGBA')
        
        # Create the overlay
        overlay = create_overlay_image(apod_data, wallpaper.size)
        
        # Composite the overlay onto the wallpaper
        composited = Image.alpha_composite(wallpaper, overlay)
        
        # Convert back to RGB for saving as JPEG (if needed) or save as PNG
        if output_path.endswith('.jpg') or output_path.endswith('.jpeg'):
            composited = composited.convert('RGB')
            composited.save(output_path, 'JPEG', quality=95)
        else:
            composited.save(output_path, 'PNG')
        
        print(f"Composited image saved to: {output_path}")
        return True
    except Exception as e:
        print(f"Error compositing overlay: {e}")
        import traceback
        traceback.print_exc()
        return False

def cleanup_directory(directory, max_size_mb):
    """
    Ensure the directory does not exceed max_size_mb.
    Deletes oldest files first until the size is within the limit.
    """
    print(f"\n5. Cleaning up directory: {directory}")
    max_size_bytes = max_size_mb * 1024 * 1024
    
    try:
        # Get all files with their full paths and sizes
        files = []
        total_size = 0
        
        for f in os.listdir(directory):
            path = os.path.join(directory, f)
            if os.path.isfile(path):
                # Skip the json cache file
                if f.endswith('.json'):
                    continue
                    
                size = os.path.getsize(path)
                total_size += size
                files.append((path, size, os.path.getmtime(path)))
        
        print(f"   Current size: {total_size / (1024*1024):.2f} MB (Limit: {max_size_mb} MB)")
        
        if total_size <= max_size_bytes:
            print("   Size is within limits. No cleanup needed.")
            return

        # Sort by modification time (oldest first)
        files.sort(key=lambda x: x[2])
        
        deleted_count = 0
        reclaimed_bytes = 0
        
        # Keep at least the 5 newest files regardless of size to prevent total wipeout in edge cases
        # (Optional safety, but good practice. Given 256MB, this is plenty for 5 images)
        files_to_keep = 1 
        if len(files) > files_to_keep:
            files_to_process = files[:-files_to_keep]
        else:
            files_to_process = []

        for path, size, mtime in files_to_process:
            if total_size <= max_size_bytes:
                break
                
            try:
                os.remove(path)
                total_size -= size
                reclaimed_bytes += size
                deleted_count += 1
                print(f"   Deleted: {os.path.basename(path)}")
            except OSError as e:
                print(f"   Error deleting {os.path.basename(path)}: {e}")
                
        print(f"   Cleanup complete. Deleted {deleted_count} files, reclaimed {reclaimed_bytes / (1024*1024):.2f} MB.")
        print(f"   New size: {total_size / (1024*1024):.2f} MB")
        
    except Exception as e:
        print(f"Error during cleanup: {e}")

def main():
    parser = argparse.ArgumentParser(description="APOD Wallpaper Overlay")
    parser.add_argument("date", nargs="?", help="Date in YYYYMMDD format")
    args = parser.parse_args()

    target_date_str = None
    if args.date:
        try:
             # Validate and convert YYYYMMDD to YYYY-MM-DD
             dt = datetime.strptime(args.date, "%Y%m%d")
             target_date_str = dt.strftime("%Y-%m-%d")
             print(f"   Target date: {target_date_str}")
        except ValueError:
             print("ERROR: Date must be in YYYYMMDD format")
             sys.exit(1)

    print("=" * 60)
    print("APOD Wallpaper Overlay - Automatic Application")
    print("=" * 60)
    
    # Get current wallpaper or download specific date
    wallpaper_path = None
    
    # Fetch APOD data first to get the URL
    print("\n2. Fetching APOD data from NASA...")
    apod_data = fetch_apod_data(target_date_str)
    
    if not apod_data:
        print("ERROR: Failed to fetch APOD data")
        sys.exit(1)
    
    # ALWAYS download the image now (Standalone Mode)
    print(f"\n   Retrieving APOD image for {apod_data.get('date')}...")
    
    if apod_data.get('media_type') == 'video':
        print(f"WARNING: Media type is '{apod_data.get('media_type')}', attempting to extract or find video thumbnail.")
        thumb = apod_data.get('thumbnail_url')
        vid_url = apod_data.get('url', '')
        
        if thumb:
            image_url = thumb
        elif 'youtube.com/embed/' in vid_url:
            vid_id = vid_url.split('embed/')[1].split('?')[0]
            image_url = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
        elif 'youtu.be/' in vid_url:
            vid_id = vid_url.split('youtu.be/')[1].split('?')[0]
            image_url = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
        else:
            image_url = vid_url
    else:
        image_url = apod_data.get('hdurl', apod_data.get('url'))
    
    if not image_url:
        print("ERROR: No image URL found in APOD data")
        sys.exit(1)
            
    # Download the image
    wallpaper_path = download_apod_image(image_url, apod_data.get('date'))

    if not wallpaper_path:
        print("ERROR: Could not get wallpaper path (current or downloaded)")
        sys.exit(1)
    
    if not os.path.exists(wallpaper_path):
        print(f"ERROR: Wallpaper file does not exist: {wallpaper_path}")
        sys.exit(1)
    
    print(f"   Base Image: {wallpaper_path}")
    
    print(f"   Title: {apod_data.get('title', 'N/A')}")
    print(f"   Date: {apod_data.get('date', 'N/A')}")
    
    # Generate output filename with date
    apod_date = apod_data.get('date', datetime.now().strftime('%Y-%m-%d'))
    output_filename = f"apod_wallpaper_{apod_date}.png"
    composited_output = os.path.join(OUTPUT_DIR, output_filename)
    
    # Create composited image
    print("\n3. Creating overlay and compositing...")
    success = composite_overlay_on_wallpaper(wallpaper_path, apod_data, composited_output)
    
    if not success:
        print("ERROR: Failed to create composited image")
        sys.exit(1)
    
    # Set the new wallpaper
    print("\n4. Setting new wallpaper...")
    if set_wallpaper(composited_output):
        # Cleanup directory to keep it under the specified limit
        cleanup_directory(OUTPUT_DIR, MAX_STORAGE_MB)

        print("\n" + "=" * 60)
        print("SUCCESS! Wallpaper with APOD overlay applied!")
        print("=" * 60)
    else:
        print("\nERROR: Failed to set wallpaper")
        sys.exit(1)

if __name__ == "__main__":
    main()
