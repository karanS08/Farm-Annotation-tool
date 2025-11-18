"""
FastAPI version of Farm Harvest Annotation Tool
Migrated from Flask to FastAPI for better performance and async support
"""
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import os
import json
import csv
from datetime import datetime
from PIL import Image
import hashlib
import re
import numpy as np
from typing import Optional, Dict, Any, List
import rasterio
from rasterio.plot import reshape_as_image

# Initialize FastAPI app
app = FastAPI(
    title="Farm Harvest Annotation Tool API",
    version="2.0",
    description="API for farm harvest annotation with Next.js frontend"
)

# Add session middleware (replaces Flask sessions)
app.add_middleware(
    SessionMiddleware,
    secret_key='harvest_annotation_secret_key_2025'  # Change this in production
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Root directory for dataset and other project files
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configuration
FARM_DATASET_DIR = os.path.join(ROOT_DIR, "farm_dataset")
CSV_FILE = os.path.join(ROOT_DIR, "harvest_annotations.csv")
FARM_INDEX_PATH = os.path.join(ROOT_DIR, 'farm_index.json')
USER_ANNOTATIONS_DIR = os.path.join(ROOT_DIR, 'annotations_by_user')
os.makedirs(USER_ANNOTATIONS_DIR, exist_ok=True)

# Thumbnail cache directory
THUMB_CACHE_DIR = os.path.join(ROOT_DIR, 'thumbnail_cache')
os.makedirs(THUMB_CACHE_DIR, exist_ok=True)


def _thumb_path_for(img_path: str) -> str:
    """Return the expected thumbnail path for an image path (hash-based filename)."""
    h = hashlib.sha256(img_path.encode('utf-8')).hexdigest()
    return os.path.join(THUMB_CACHE_DIR, f"{h}.png")


def make_thumbnail(source_path: str, width: int = 300, height: int = 300) -> Optional[str]:
    """Generate (and cache) a thumbnail for `source_path` with the requested size.
    Returns the filesystem path to the thumbnail image, or None on failure.
    Handles multispectral TIFF files using rasterio.
    """
    if not os.path.isfile(source_path):
        return None

    # Deterministic cache name that includes size
    base_h = hashlib.sha256(source_path.encode('utf-8')).hexdigest()
    thumb_name = f"{base_h}_{width}x{height}.png"
    thumb_path = os.path.join(THUMB_CACHE_DIR, thumb_name)

    if os.path.isfile(thumb_path):
        return thumb_path

    try:
        # Check if it's a TIFF file that might need special handling
        if source_path.lower().endswith(('.tif', '.tiff')):
            # First, try using rasterio for multispectral/complex TIFFs
            try:
                with rasterio.open(source_path) as src:
                    # Read the data
                    data = src.read()
                    
                    print(f"  - TIFF bands: {data.shape[0]}, size: {data.shape[1]}x{data.shape[2]}")
                    
                    # Handle different band counts
                    if data.shape[0] >= 3:
                        # Multi-band: Use first 3 bands as RGB (or bands that make visual sense)
                        # Typically bands 1-3 are Red, Green, Blue or NIR, Red, Green
                        # Try common combinations
                        if data.shape[0] >= 4:
                            # For 4+ bands, try to pick RGB-like bands (often 3,2,1 or 4,3,2)
                            # Use bands 3,2,1 (0-indexed: 2,1,0) which often corresponds to RGB
                            rgb = np.stack([
                                data[2, :, :],  # Red
                                data[1, :, :],  # Green
                                data[0, :, :]   # Blue
                            ], axis=-1)
                        else:
                            # 3 bands: assume RGB
                            rgb = np.stack([
                                data[0, :, :],
                                data[1, :, :],
                                data[2, :, :]
                            ], axis=-1)
                    elif data.shape[0] == 1:
                        # Single band: grayscale
                        rgb = data[0, :, :]
                    else:
                        raise ValueError(f"Unsupported band count: {data.shape[0]}")
                    
                    # Normalize to 0-255 range
                    if rgb.dtype in [np.float32, np.float64]:
                        # Float data
                        rgb_min, rgb_max = rgb.min(), rgb.max()
                        if rgb_max > rgb_min:
                            rgb = ((rgb - rgb_min) / (rgb_max - rgb_min) * 255).astype(np.uint8)
                        else:
                            rgb = np.zeros_like(rgb, dtype=np.uint8)
                    elif rgb.dtype == np.uint16:
                        # 16-bit integer
                        rgb_min, rgb_max = rgb.min(), rgb.max()
                        if rgb_max > rgb_min:
                            rgb = ((rgb.astype(np.float32) - rgb_min) / (rgb_max - rgb_min) * 255).astype(np.uint8)
                        else:
                            rgb = np.zeros_like(rgb, dtype=np.uint8)
                    elif rgb.dtype != np.uint8:
                        # Other types: try to normalize
                        rgb_min, rgb_max = rgb.min(), rgb.max()
                        if rgb_max > rgb_min:
                            rgb = ((rgb.astype(np.float32) - rgb_min) / (rgb_max - rgb_min) * 255).astype(np.uint8)
                        else:
                            rgb = np.zeros_like(rgb, dtype=np.uint8)
                    
                    # Create PIL Image
                    if len(rgb.shape) == 3:
                        im = Image.fromarray(rgb, mode='RGB')
                    else:
                        im = Image.fromarray(rgb, mode='L').convert('RGB')
                    
                    # Create thumbnail
                    im.thumbnail((width, height), Image.LANCZOS)
                    im.save(thumb_path, format='PNG', optimize=True)
                    
                    print(f"✓ Generated thumbnail for multispectral TIFF: {os.path.basename(source_path)}")
                    return thumb_path
                    
            except Exception as e:
                print(f"  - Rasterio failed, trying PIL: {e}")
                # Fall back to PIL for simpler TIFFs
                try:
                    with Image.open(source_path) as im:
                        # For multi-page TIFFs, seek to first page
                        im.seek(0)
                        
                        # Convert to RGB mode based on current mode
                        if im.mode in ('RGB', 'RGBA'):
                            im = im.convert('RGB')
                        elif im.mode == 'L':
                            im = im.convert('RGB')
                        elif im.mode in ('I', 'I;16', 'I;16B', 'I;16L', 'I;16N'):
                            # 16-bit integer modes
                            arr = np.array(im, dtype=np.float32)
                            arr_min, arr_max = arr.min(), arr.max()
                            if arr_max > arr_min:
                                arr = ((arr - arr_min) / (arr_max - arr_min) * 255).astype(np.uint8)
                            else:
                                arr = np.zeros_like(arr, dtype=np.uint8)
                            im = Image.fromarray(arr, mode='L').convert('RGB')
                        elif im.mode == 'F':
                            # 32-bit floating point
                            arr = np.array(im)
                            arr_min, arr_max = arr.min(), arr.max()
                            if arr_max > arr_min:
                                arr = ((arr - arr_min) / (arr_max - arr_min) * 255).astype(np.uint8)
                            else:
                                arr = np.zeros_like(arr, dtype=np.uint8)
                            im = Image.fromarray(arr, mode='L').convert('RGB')
                        else:
                            im = im.convert('RGB')
                        
                        # Create thumbnail
                        im.thumbnail((width, height), Image.LANCZOS)
                        im.save(thumb_path, format='PNG', optimize=True)
                        
                    print(f"✓ Generated thumbnail for TIFF using PIL: {os.path.basename(source_path)}")
                    return thumb_path
                except Exception as pil_error:
                    print(f"✗ Both rasterio and PIL failed for {source_path}")
                    print(f"  - Rasterio error: {e}")
                    print(f"  - PIL error: {pil_error}")
                    import traceback
                    traceback.print_exc()
                    return None
        else:
            # Standard image processing for PNG, JPG, etc.
            with Image.open(source_path) as im:
                im = im.convert('RGB')
                im.thumbnail((width, height), Image.LANCZOS)
                im.save(thumb_path, format='PNG', optimize=True)
            return thumb_path
    except Exception as e:
        print(f"✗ Thumbnail generation error for {source_path}: {e}")
        import traceback
        traceback.print_exc()
        return None


# Load or build farm index once (memory efficient: only farm ids and paths stored)
_FARM_INDEX: Optional[List[Dict[str, str]]] = None


def build_farm_index(force: bool = False) -> List[Dict[str, str]]:
    global _FARM_INDEX
    if _FARM_INDEX is not None and not force:
        return _FARM_INDEX
    
    farm_list = []
    if os.path.isdir(FARM_DATASET_DIR):
        try:
            farm_dirs = [d for d in os.listdir(FARM_DATASET_DIR)
                         if os.path.isdir(os.path.join(FARM_DATASET_DIR, d)) and d != "0"]
            farm_dirs.sort()
            for farm_id in farm_dirs:
                farm_path = os.path.join(FARM_DATASET_DIR, farm_id)
                farm_list.append({'farm_id': farm_id, 'farm_path': farm_path})

            if farm_list:
                _FARM_INDEX = farm_list
                try:
                    with open(FARM_INDEX_PATH, 'w') as fh:
                        json.dump(_FARM_INDEX, fh)
                except Exception:
                    pass
                return _FARM_INDEX
        except Exception:
            farm_list = []

    # Fallback: try loading prebuilt farm_index.json
    if os.path.exists(FARM_INDEX_PATH) and not force:
        try:
            with open(FARM_INDEX_PATH, 'r') as fh:
                _FARM_INDEX = json.load(fh)
                return _FARM_INDEX
        except Exception:
            pass

    _FARM_INDEX = farm_list
    return _FARM_INDEX


# Build index on startup
build_farm_index()


def parse_date_from_filename(filename_or_path: str) -> tuple:
    """Parse date from a filename (or full path). Return a sortable tuple (year, month_num, day)."""
    try:
        filename = os.path.basename(filename_or_path)
    except Exception:
        filename = str(filename_or_path)
    filename_lower = filename.lower()
    
    # Try the new enhanced dataset format: YYYY_MM_DD.png
    enhanced_pattern = r'^(\d{4})_(\d{1,2})_(\d{1,2})\.png$'
    match = re.search(enhanced_pattern, filename_lower)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        return (year, month, day)
    
    # Month name mapping
    month_map = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    
    # Try different legacy patterns
    patterns = [
        r'([a-z]+)_(\d{4})',
        r'(\d+)([a-z]+),(\d{4})',
        r'(\d+)([a-z]+)(\d{4})',
        r'([a-z]+)(\d+)_(\d{4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename_lower)
        if match:
            groups = match.groups()
            
            if len(groups) == 2:
                month_str, year_str = groups
                if month_str in month_map:
                    return (int(year_str), month_map[month_str], 1)
                    
            elif len(groups) == 3:
                if groups[0].isdigit():
                    day_str, month_str, year_str = groups
                    if month_str in month_map:
                        return (int(year_str), month_map[month_str], int(day_str))
                else:
                    month_str, day_str, year_str = groups
                    if month_str in month_map:
                        return (int(year_str), month_map[month_str], int(day_str))
    
    # Try to extract year at least
    year_match = re.search(r'20\d{2}', filename)
    if year_match:
        year = int(year_match.group())
        return (year, 0, 0)

    # Last resort: use file modification time
    try:
        if os.path.exists(filename_or_path):
            mtime = os.path.getmtime(filename_or_path)
            dt = datetime.fromtimestamp(mtime)
            return (dt.year, dt.month, dt.day)
    except Exception:
        pass

    return (2024, 0, 0)


_FARM_GROUPS_CACHE: Optional[List[Dict[str, Any]]] = None
_FARM_GROUPS_CACHE_TS: float = 0


def find_farm_groups() -> List[Dict[str, Any]]:
    """Scan farm_dataset folder and organize by farm ID and time series."""
    global _FARM_GROUPS_CACHE, _FARM_GROUPS_CACHE_TS
    
    CACHE_TTL = 5.0
    now_ts = datetime.now().timestamp()
    if _FARM_GROUPS_CACHE and (now_ts - _FARM_GROUPS_CACHE_TS) < CACHE_TTL:
        return _FARM_GROUPS_CACHE

    groups = []
    farms_index = build_farm_index()
    
    if farms_index:
        for entry in farms_index:
            farm_id = entry.get('farm_id')
            farm_path = entry.get('farm_path') or os.path.join(FARM_DATASET_DIR, farm_id)
            if not os.path.isdir(farm_path):
                continue

            images = []
            try:
                for file in os.listdir(farm_path):
                    if file.lower().endswith(('.tif', '.tiff', '.png')):
                        images.append(os.path.join(farm_path, file))
            except Exception:
                images = []

            images.sort(key=lambda x: parse_date_from_filename(x))
            if images:
                groups.append({
                    'farm_id': farm_id,
                    'images': images,
                    'image_count': len(images)
                })
    else:
        # Fallback: scan FARM_DATASET_DIR directly
        if os.path.isdir(FARM_DATASET_DIR):
            farm_dirs = [d for d in os.listdir(FARM_DATASET_DIR)
                         if os.path.isdir(os.path.join(FARM_DATASET_DIR, d)) and d != '0']
            farm_dirs.sort()
            for farm_id in farm_dirs:
                farm_path = os.path.join(FARM_DATASET_DIR, farm_id)
                images = []
                try:
                    for file in os.listdir(farm_path):
                        if file.lower().endswith(('.tif', '.tiff', '.png')):
                            images.append(os.path.join(farm_path, file))
                except Exception:
                    images = []

                images.sort(key=lambda x: parse_date_from_filename(x))
                if images:
                    groups.append({
                        'farm_id': farm_id,
                        'images': images,
                        'image_count': len(images)
                    })

    _FARM_GROUPS_CACHE = groups
    _FARM_GROUPS_CACHE_TS = datetime.now().timestamp()
    return groups


# API Routes

@app.get("/")
async def index():
    """API documentation endpoint"""
    return {
        'message': 'Farm Harvest Annotation Tool API',
        'version': '2.0',
        'framework': 'FastAPI',
        'frontend': 'Next.js frontend available at http://localhost:3000',
        'endpoints': {
            'status': '/api/status',
            'farm': '/api/farm/<farm_id>',
            'navigate': '/api/navigate',
            'save': '/api/save_annotation',
            'skip': '/api/skip_farm',
            'reset': '/api/reset',
            'thumbnail': '/api/thumbnail'
        }
    }


@app.get("/api/farm/{farm_id}")
async def get_farm_data(farm_id: str):
    """Get data for a specific farm by id (lazy-load images)."""
    farms = build_farm_index()
    farm_entry = next((f for f in farms if f['farm_id'] == farm_id), None)
    
    if farm_entry is None:
        possible_path = os.path.join(FARM_DATASET_DIR, farm_id)
        if os.path.isdir(possible_path):
            farm_entry = {'farm_id': farm_id, 'farm_path': possible_path}
            farms.append(farm_entry)
        else:
            raise HTTPException(status_code=400, detail='Invalid farm id')
    
    if not farm_entry:
        raise HTTPException(status_code=400, detail='Invalid farm id')

    farm_path = farm_entry['farm_path']
    images = [os.path.join(farm_path, f) for f in os.listdir(farm_path)
              if f.lower().endswith(('.tif', '.tiff', '.png'))]
    images.sort(key=lambda x: parse_date_from_filename(x))

    thumbnails = []
    for idx, img_path in enumerate(images):
        filename = os.path.basename(img_path)
        try:
            date_tuple = parse_date_from_filename(img_path)
            year, month, day = date_tuple
            month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            if month > 0:
                date_display = f"{month_names[month]} {day}, {year}" if day > 0 else f"{month_names[month]} {year}"
            else:
                date_display = f"{year}"

            thumbnails.append({
                'index': idx,
                'filename': filename,
                'date_display': date_display,
                'sort_date': date_tuple,
                'original_path': os.path.join(farm_path, filename)
            })
        except Exception:
            continue

    thumbnails.sort(key=lambda x: x['sort_date'])

    # Try to load the user's previous selection for this farm
    selected_index = None
    try:
        annotator = 'anonymous'
        from fastapi import Request as FastapiRequest
        import inspect
        for frame in inspect.stack():
            if 'request' in frame.frame.f_locals:
                req = frame.frame.f_locals['request']
                if hasattr(req, 'session'):
                    annotator = req.session.get('annotator', 'anonymous')
                break
        user_dir = os.path.join(USER_ANNOTATIONS_DIR, annotator)
        latest_json = os.path.join(user_dir, 'latest.json')
        if os.path.exists(latest_json):
            with open(latest_json, 'r', encoding='utf-8') as jf:
                latest = json.load(jf)
            if farm_id in latest and 'selected_index' in latest[farm_id]:
                selected_index = latest[farm_id]['selected_index']
    except Exception:
        selected_index = None

    return {
        'farm_id': farm_id,
        'image_count': len(images),
        'thumbnails': thumbnails,
        'selected_index': selected_index
    }


@app.get("/api/admin/tasks")
async def admin_tasks():
    """Admin diagnostics - return filesystem-derived counts."""
    groups = find_farm_groups()
    return {'total_farms': len(groups)}


@app.post("/api/login")
async def login(request: Request):
    """Login endpoint for annotators"""
    data = await request.json()
    name = data.get('name')
    if not name or not str(name).strip():
        raise HTTPException(status_code=400, detail='Name required')
    
    name = str(name).strip()
    request.session['annotator'] = name
    
    # Ensure user's annotation folder exists
    user_dir = os.path.join(USER_ANNOTATIONS_DIR, name)
    os.makedirs(user_dir, exist_ok=True)
    return {'success': True, 'annotator': name}


@app.post("/api/claim_batch")
async def claim_batch(request: Request):
    """Claim a batch of farms for the annotator (simple session-based)."""
    annotator = request.session.get('annotator')
    if not annotator:
        raise HTTPException(status_code=403, detail='Annotator not logged in')

    data = await request.json()
    batch_size = int(data.get('batch_size', 100))

    groups = find_farm_groups()
    claimed = set(request.session.get('claimed_farms', []))
    farm_ids = []
    
    for g in groups:
        if g['farm_id'] in claimed:
            continue
        farm_ids.append(g['farm_id'])
        if len(farm_ids) >= batch_size:
            break

    claimed.update(farm_ids)
    request.session['claimed_farms'] = list(claimed)
    request.session['current_batch'] = {
        'annotator': annotator,
        'farm_ids': farm_ids,
        'claimed_at': datetime.now().isoformat()
    }

    return {'success': True, 'farm_ids': farm_ids}


@app.post("/api/release_batch")
async def release_batch(request: Request):
    """Release claimed batch"""
    annotator = request.session.get('annotator')
    if not annotator:
        raise HTTPException(status_code=403, detail='Annotator not logged in')

    batch = request.session.get('current_batch')
    if not batch or batch.get('annotator') != annotator:
        raise HTTPException(status_code=400, detail='No batch claimed by this annotator')

    farm_ids = batch.get('farm_ids', [])
    claimed = set(request.session.get('claimed_farms', []))
    for fid in farm_ids:
        claimed.discard(fid)
    request.session['claimed_farms'] = list(claimed)
    request.session.pop('current_batch', None)
    return {'success': True, 'released': farm_ids}


@app.get("/api/user_status")
async def user_status(request: Request):
    """Get user annotation status"""
    annotator = request.session.get('annotator')
    if not annotator:
        return {'logged_in': False}

    batch = request.session.get('current_batch')
    completed = 0
    
    try:
        user_dir = os.path.join(USER_ANNOTATIONS_DIR, annotator)
        if os.path.isdir(user_dir):
            for fn in os.listdir(user_dir):
                if fn.endswith('.csv'):
                    with open(os.path.join(user_dir, fn), 'r', encoding='utf-8') as fh:
                        completed += sum(1 for _ in fh)
    except Exception:
        completed = 0

    currently_assigned = len(request.session.get('current_batch', {}).get('farm_ids', []))

    return {
        'logged_in': True,
        'annotator': annotator,
        'current_batch': batch,
        'completed_annotations': completed,
        'currently_assigned': currently_assigned
    }


@app.post("/api/navigate")
async def navigate(request: Request):
    """Navigate to previous/next farm"""
    data = await request.json()
    direction = data.get('direction')
    groups = find_farm_groups()
    all_farms = [g['farm_id'] for g in groups]

    if not all_farms:
        return {'current_farm': None}

    cur_idx = None
    if isinstance(request.session.get('current_farm'), int):
        cur_idx = request.session.get('current_farm')
    elif request.session.get('current_farm_id'):
        try:
            cur_idx = all_farms.index(request.session.get('current_farm_id'))
        except ValueError:
            cur_idx = 0
    else:
        cur_idx = 0

    # Clamp
    if cur_idx < 0:
        cur_idx = 0
    if cur_idx >= len(all_farms):
        cur_idx = len(all_farms) - 1

    if direction == 'prev' and cur_idx > 0:
        cur_idx -= 1
    elif direction == 'next' and cur_idx < len(all_farms) - 1:
        cur_idx += 1

    request.session['current_farm'] = cur_idx
    request.session['current_farm_id'] = all_farms[cur_idx]

    return {
        'current_farm': request.session.get('current_farm_id'),
        'current_index': cur_idx,
        'total_farms': len(all_farms)
    }


@app.post("/api/save_annotation")
async def save_annotation(request: Request):
    """Save annotation selection"""
    data = await request.json()
    farm_id = data.get('farm_id')
    selected_image = data.get('selected_image')
    image_path = data.get('image_path')
    total_images = data.get('total_images', None)

    # Backwards-compatibility
    if not farm_id and data.get('farm_index') is not None:
        try:
            idx = int(data.get('farm_index'))
            groups = find_farm_groups()
            if 0 <= idx < len(groups):
                farm_id = groups[idx]['farm_id']
        except Exception:
            farm_id = None

    if farm_id and (not selected_image or not image_path):
        sel_idx = data.get('selected_image_index')
        try:
            if sel_idx is not None:
                sel_idx = int(sel_idx)
                farm_path = os.path.join(FARM_DATASET_DIR, farm_id)
                if os.path.isdir(farm_path):
                    imgs = [f for f in os.listdir(farm_path) if f.lower().endswith(('.tif', '.tiff', '.png'))]
                    imgs.sort(key=lambda x: parse_date_from_filename(os.path.basename(x)))
                    if 0 <= sel_idx < len(imgs):
                        selected_image = imgs[sel_idx]
                        image_path = os.path.join(farm_path, selected_image)
                        total_images = total_images or len(imgs)
        except Exception:
            pass
    
    annotator = request.session.get('annotator', 'anonymous')

    if not farm_id or not selected_image or not image_path:
        raise HTTPException(status_code=400, detail='Missing data')

    timestamp = datetime.now().isoformat()

    try:
        write_header = not os.path.exists(CSV_FILE)
        with open(CSV_FILE, "a", newline="", encoding='utf-8') as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["farm_id", "selected_image", "image_path", "total_images", "timestamp"])
            writer.writerow([farm_id, selected_image, image_path, total_images, timestamp])
    except Exception:
        pass

    # Also write per-annotator CSV and persist latest selection in JSON
    try:
        annotator_name = request.session.get('annotator', 'anonymous')
        user_dir = os.path.join(USER_ANNOTATIONS_DIR, annotator_name)
        os.makedirs(user_dir, exist_ok=True)
        user_csv = os.path.join(user_dir, f'annotations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        with open(user_csv, 'a', newline='', encoding='utf-8') as uf:
            uw = csv.writer(uf)
            uw.writerow([farm_id, selected_image, image_path, total_images, timestamp])

        # Persist latest selection in JSON
        latest_json = os.path.join(user_dir, 'latest.json')
        try:
            if os.path.exists(latest_json):
                with open(latest_json, 'r', encoding='utf-8') as jf:
                    latest = json.load(jf)
            else:
                latest = {}
        except Exception:
            latest = {}
        # Find the selected index for this image
        selected_index = None
        farm_path = os.path.join(FARM_DATASET_DIR, farm_id)
        if os.path.isdir(farm_path):
            imgs = [f for f in os.listdir(farm_path) if f.lower().endswith(('.tif', '.tiff', '.png'))]
            imgs.sort(key=lambda x: parse_date_from_filename(os.path.basename(x)))
            try:
                selected_index = imgs.index(os.path.basename(selected_image))
            except Exception:
                selected_index = None
        latest[farm_id] = {
            'selected_image': selected_image,
            'selected_index': selected_index,
            'timestamp': timestamp
        }
        with open(latest_json, 'w', encoding='utf-8') as jf:
            json.dump(latest, jf)
    except Exception:
        pass

    return {
        'success': True,
        'message': f'Saved selection for Farm {farm_id}: {selected_image}'
    }


@app.get("/thumbnails/{farm_id}/{filename:path}")
async def serve_image(farm_id: str, filename: str):
    """Serve original images from the dataset safely. Converts TIFF to PNG for browser compatibility."""
    safe_farm = os.path.join(FARM_DATASET_DIR, farm_id)
    if not os.path.isdir(safe_farm):
        raise HTTPException(status_code=404, detail='Invalid farm id')
    
    file_path = os.path.join(safe_farm, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail='File not found')
    
    # If it's a TIFF file, convert to PNG for browser display
    if filename.lower().endswith(('.tif', '.tiff')):
        # Generate a web-viewable version at reasonable size
        thumb_path = make_thumbnail(file_path, width=800, height=800)
        if thumb_path and os.path.isfile(thumb_path):
            response = FileResponse(thumb_path, media_type='image/png')
            response.headers["Cache-Control"] = "public, max-age=2592000"
            return response
    
    return FileResponse(file_path)


@app.get("/thumbs/{farm_id}/{filename:path}")
async def serve_thumb(farm_id: str, filename: str):
    """Serve a pre-generated thumbnail from thumbnail_cache/ if present."""
    img_full = os.path.join(FARM_DATASET_DIR, farm_id, filename)
    
    if not os.path.isfile(img_full):
        raise HTTPException(status_code=404, detail='File not found')
    
    sized_thumb = None
    
    # Look for any sized thumbnail for this image in cache
    try:
        base_hash = hashlib.sha256(img_full.encode('utf-8')).hexdigest()
        for fn in os.listdir(THUMB_CACHE_DIR):
            if fn.startswith(base_hash):
                sized_thumb = os.path.join(THUMB_CACHE_DIR, fn)
                break
    except Exception:
        pass

    if sized_thumb and os.path.isfile(sized_thumb):
        response = FileResponse(sized_thumb, media_type='image/png')
        response.headers["Cache-Control"] = "public, max-age=2592000"
        return response

    # Fallback: try to create thumbnail on-demand
    thumb_path = make_thumbnail(img_full, width=300, height=300)
    if thumb_path and os.path.isfile(thumb_path):
        response = FileResponse(thumb_path, media_type='image/png')
        response.headers["Cache-Control"] = "public, max-age=2592000"
        return response

    # Final fallback: convert TIFF to PNG if needed
    if img_full.lower().endswith(('.tif', '.tiff')):
        raise HTTPException(status_code=500, detail='Failed to generate thumbnail for TIFF')
    
    return FileResponse(img_full)


@app.get("/api/thumbnail")
async def api_thumbnail(
    farm_id: Optional[str] = Query(None),
    filename: Optional[str] = Query(None),
    w: int = Query(300),
    h: int = Query(300)
):
    """On-demand thumbnail endpoint. Query params: farm_id, filename, w, h"""
    if not farm_id or not filename:
        raise HTTPException(status_code=400, detail='farm_id and filename required')

    source = os.path.join(FARM_DATASET_DIR, farm_id, filename)
    
    if not os.path.isfile(source):
        raise HTTPException(status_code=404, detail='file not found')
    
    thumb_path = make_thumbnail(source, width=w, height=h)
    
    if thumb_path and os.path.isfile(thumb_path):
        response = FileResponse(thumb_path, media_type='image/png')
        response.headers["Cache-Control"] = "public, max-age=2592000"
        return response

    # For TIFF files, we must convert - browsers can't display raw TIFF
    if source.lower().endswith(('.tif', '.tiff')):
        raise HTTPException(status_code=500, detail='Failed to generate thumbnail for TIFF')
    
    # For other formats, serve original
    return FileResponse(source)


@app.post("/api/skip_farm")
async def skip_farm(request: Request):
    """Skip current farm without saving selection"""
    data = await request.json()
    farm_index = int(data.get('farm_index'))
    groups = find_farm_groups()
    
    if farm_index < len(groups) - 1:
        request.session['current_farm'] = farm_index + 1
        new_farm_id = groups[farm_index + 1]['farm_id']
        return {
            'success': True,
            'current_farm': request.session['current_farm'],
            'current_farm_id': new_farm_id,
            'current_index': farm_index + 1,
            'total_farms': len(groups),
            'message': f'Skipped farm {groups[farm_index]["farm_id"]}'
        }
    else:
        return {
            'success': True,
            'completed': True,
            'message': 'All farms processed!'
        }


@app.get("/api/status")
async def get_status(request: Request):
    """Get current annotation status"""
    groups = find_farm_groups()
    current_farm_index = request.session.get('current_farm', 0)

    current_farm_id = None
    try:
        if 0 <= current_farm_index < len(groups):
            current_farm_id = groups[current_farm_index]['farm_id']
    except Exception:
        current_farm_id = None

    return {
        'total_farms': len(groups),
        'current_farm_index': current_farm_index,
        'current_farm_id': current_farm_id,
        'completed': current_farm_index >= len(groups)
    }


@app.get("/api/reset")
async def reset_session(request: Request):
    """Reset annotation session"""
    request.session['current_farm'] = 0
    return {'success': True, 'message': 'Session reset'}


if __name__ == '__main__':
    import uvicorn
    
    print(f"🌾 Farm Harvest Annotation Server (FastAPI)")
    print(f"📁 Farm dataset: {FARM_DATASET_DIR}")
    print(f"💾 Annotations CSV: {CSV_FILE}")
    print(f"🖼️  Image formats: TIFF (.tif/.tiff) and PNG - auto-converted to PNG thumbnails")
    print(f"📦 Thumbnail cache: {THUMB_CACHE_DIR}")
    print(f"🌐 Starting server at http://localhost:5005")
    print(f"🔄 CORS enabled for: http://localhost:3000, http://localhost:3001")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=5005,
        reload=True,
        log_level="info"
    )
