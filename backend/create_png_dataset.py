#!/usr/bin/env python3
"""
Fast Multi-threaded PNG Dataset Creator
Converts TIF images to PNG with 10-core parallel processing for efficiency
"""

import os
import rasterio
import numpy as np
from PIL import Image
from datetime import datetime
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import time

# Global variables for thread safety
print_lock = Lock()
progress_lock = Lock()
completed_farms = 0
total_farms = 0

def thread_safe_print(message):
    """Thread-safe printing"""
    with print_lock:
        print(message)

def update_progress():
    """Thread-safe progress update"""
    global completed_farms
    with progress_lock:
        completed_farms += 1
        if completed_farms % 10 == 0 or completed_farms == total_farms:
            thread_safe_print(f"✅ Progress: {completed_farms}/{total_farms} farms completed ({completed_farms/total_farms*100:.1f}%)")

def aggressive_stretch(rgb_array, percentile_range=(0.5, 99.5)):
    """Apply aggressive contrast stretching for better visualization"""
    result = np.zeros_like(rgb_array, dtype=np.float64)
    for i in range(3):
        band = rgb_array[:, :, i].astype(np.float64)
        non_zero = band[band > 0]
        if len(non_zero) > 0:
            p_low, p_high = np.percentile(non_zero, percentile_range)
        else:
            p_low, p_high = np.percentile(band, percentile_range)
        if p_high > p_low:
            result[:, :, i] = (band - p_low) / (p_high - p_low)
        else:
            result[:, :, i] = band / np.max(band) if np.max(band) > 0 else band
    return np.clip(result * 255, 0, 255).astype(np.uint8)

def convert_tif_to_png(tif_path, png_path, size=(500, 500)):
    """Convert TIF to PNG with RGB band mapping and aggressive stretching"""
    try:
        with rasterio.open(tif_path) as src:
            bands = src.read()
            
            if bands.shape[0] >= 4:
                # RGB mapping: R=Band4, G=Band3, B=Band2
                rgb_composite = np.stack([bands[3], bands[2], bands[1]], axis=-1)
                
                # Handle invalid values
                if np.any(np.isnan(rgb_composite)) or np.any(np.isinf(rgb_composite)):
                    rgb_composite = np.nan_to_num(rgb_composite, nan=0.0, posinf=0.0, neginf=0.0)
                
                # Apply aggressive contrast stretching
                rgb_composite = aggressive_stretch(rgb_composite)
                
                # Create PIL image and resize
                img = Image.fromarray(rgb_composite)
                img = img.resize(size, Image.Resampling.LANCZOS)
                
                # Save as PNG
                img.save(png_path, format='PNG', optimize=True)
                return True
            else:
                return False
                
    except Exception as e:
        thread_safe_print(f"❌ Error converting {tif_path}: {e}")
        return False

def parse_date_from_path_and_filename(folder_path, filename):
    """Enhanced date parsing from both folder structure and filename"""
    parts = Path(folder_path).parts
    
    # Method 1: Parse from folder structure (e.g., imgs_24_25/Oct/11Oct/)
    month_name = None
    day_month = None
    
    for part in parts:
        if part in ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'March', 'April']:
            month_name = part
        elif any(part.endswith(month) for month in ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'March', 'April']):
            day_month = part
    
    if month_name and day_month:
        day_match = re.match(r'(\d+)', day_month)
        if day_match:
            day = int(day_match.group(1))
            month_map = {
                'Oct': 10, 'Nov': 11, 'Dec': 12,
                'Jan': 1, 'Feb': 2, 'March': 3, 'April': 4
            }
            month = month_map.get(month_name)
            if month:
                year = 2024 if month >= 10 else 2025
                return (year, month, day)
    
    # Method 2: Parse from filename (fallback)
    filename_lower = filename.lower()
    month_map = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
        'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
        'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
        'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    
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
    
    # Default fallback
    return (2024, 1, 1)

def find_all_temporal_images(imgs_24_25_dir):
    """Find all temporal images in imgs_24_25 directory"""
    temporal_images = []
    
    for root, dirs, files in os.walk(imgs_24_25_dir):
        for file in files:
            if file.lower().endswith('.tif') and not file.endswith('_udm2.tif'):
                file_path = os.path.join(root, file)
                date_tuple = parse_date_from_path_and_filename(root, file)
                
                if date_tuple:
                    year, month, day = date_tuple
                    # Create standardized filename
                    png_name = f"{year:04d}_{month:02d}_{day:02d}.png"
                    temporal_images.append((date_tuple, file_path, png_name))
    
    # Sort by date and remove duplicates
    temporal_images.sort(key=lambda x: x[0])
    unique_images = {}
    for date_tuple, file_path, png_name in temporal_images:
        if png_name not in unique_images:
            unique_images[png_name] = (date_tuple, file_path, png_name)
    
    return list(unique_images.values())

def process_single_farm(args):
    """Process a single farm - convert all TIF images to PNG"""
    farm_id, farm_input_dir, farm_output_dir, temporal_images = args
    
    try:
        # Create output directory
        os.makedirs(farm_output_dir, exist_ok=True)
        
        images_processed = 0
        
        # Process temporal images
        for date_tuple, file_path, png_name in temporal_images:
            png_output_path = os.path.join(farm_output_dir, png_name)
            if convert_tif_to_png(file_path, png_output_path):
                images_processed += 1
        
        # Process existing farm images (legacy)
        if os.path.exists(farm_input_dir):
            for file in os.listdir(farm_input_dir):
                if file.lower().endswith(('.tif', '.tiff')):
                    tif_path = os.path.join(farm_input_dir, file)
                    png_name = f"legacy_{os.path.splitext(file)[0]}.png"
                    png_output_path = os.path.join(farm_output_dir, png_name)
                    if convert_tif_to_png(tif_path, png_output_path):
                        images_processed += 1
        
        update_progress()
        return f"Farm {farm_id}: {images_processed} images converted"
        
    except Exception as e:
        update_progress()
        return f"Farm {farm_id}: ERROR - {e}"

def create_png_dataset_parallel(imgs_24_25_dir, current_farm_dataset_dir, output_dir, max_workers=10):
    """Create PNG dataset using parallel processing"""
    global total_farms, completed_farms
    
    thread_safe_print("🚀 Fast Multi-threaded PNG Dataset Creator")
    thread_safe_print("=" * 50)
    thread_safe_print(f"🧵 Using {max_workers} parallel threads")
    thread_safe_print(f"📁 Source images: {imgs_24_25_dir}")
    thread_safe_print(f"📂 Current farms: {current_farm_dataset_dir}")
    thread_safe_print(f"📤 Output directory: {output_dir}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Find all temporal images
    thread_safe_print("\n🔍 Scanning temporal images...")
    temporal_images = find_all_temporal_images(imgs_24_25_dir)
    thread_safe_print(f"📊 Found {len(temporal_images)} unique temporal images")
    
    # Get existing farms
    existing_farms = []
    if os.path.exists(current_farm_dataset_dir):
        existing_farms = [d for d in os.listdir(current_farm_dataset_dir) 
                         if os.path.isdir(os.path.join(current_farm_dataset_dir, d)) 
                         and d != "0"]
        existing_farms.sort()
    
    total_farms = len(existing_farms)
    completed_farms = 0
    
    thread_safe_print(f"🏠 Processing {total_farms} farms in parallel...")
    
    # Prepare arguments for parallel processing
    farm_args = []
    for farm_id in existing_farms:
        farm_input_dir = os.path.join(current_farm_dataset_dir, farm_id)
        farm_output_dir = os.path.join(output_dir, farm_id)
        farm_args.append((farm_id, farm_input_dir, farm_output_dir, temporal_images))
    
    # Process farms in parallel
    start_time = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_farm = {executor.submit(process_single_farm, args): args[0] for args in farm_args}
        
        for future in as_completed(future_to_farm):
            farm_id = future_to_farm[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                thread_safe_print(f"❌ Farm {farm_id} failed: {e}")
                update_progress()
    
    end_time = time.time()
    
    thread_safe_print(f"\n✅ Dataset creation completed!")
    thread_safe_print(f"⏱️  Total time: {end_time - start_time:.2f} seconds")
    thread_safe_print(f"📁 Output: {output_dir}")
    thread_safe_print(f"🏠 Farms processed: {total_farms}")
    thread_safe_print(f"📷 Images per farm: {len(temporal_images)} + legacy images")
    thread_safe_print(f"🖼️  Format: PNG (optimized for web)")

def main():
    # Configuration
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    imgs_24_25_dir = os.path.join(project_root, "imgs_24_25")
    current_farm_dataset_dir = os.path.join(project_root, "farm_dataset")
    output_dir = os.path.join(project_root, "png_farm_dataset")
    
    # Validate input directories
    if not os.path.exists(imgs_24_25_dir):
        print(f"❌ imgs_24_25 directory not found: {imgs_24_25_dir}")
        return
    
    if not os.path.exists(current_farm_dataset_dir):
        print(f"❌ farm_dataset directory not found: {current_farm_dataset_dir}")
        return
    
    # Create PNG dataset with parallel processing
    create_png_dataset_parallel(imgs_24_25_dir, current_farm_dataset_dir, output_dir, max_workers=10)

if __name__ == "__main__":
    main()

import os
import numpy as np
import rasterio
from PIL import Image
from datetime import datetime
import re
from pathlib import Path

def aggressive_stretch(rgb_array, percentile_range=(0.5, 99.5)):
    """
    Apply aggressive contrast stretching to RGB array
    Same function as used in the Flask app
    """
    result = np.zeros_like(rgb_array, dtype=np.float64)
    for i in range(3):
        band = rgb_array[:, :, i].astype(np.float64)
        non_zero = band[band > 0]
        if len(non_zero) > 0:
            p_low, p_high = np.percentile(non_zero, percentile_range)
        else:
            p_low, p_high = np.percentile(band, percentile_range)
        if p_high > p_low:
            result[:, :, i] = (band - p_low) / (p_high - p_low)
        else:
            result[:, :, i] = band / np.max(band) if np.max(band) > 0 else band
    return np.clip(result * 255, 0, 255).astype(np.uint8)

def process_tiff_to_png(tiff_path, output_path, target_size=(800, 800)):
    """
    Convert TIFF to PNG with enhanced contrast and proper RGB bands
    """
    try:
        with rasterio.open(tiff_path) as src:
            bands = src.read()
            
            if bands.shape[0] >= 4:
                # Create RGB image with R=Band4, G=Band3, B=Band2
                rgb_composite = np.stack([bands[3], bands[2], bands[1]], axis=-1)
                
                # Handle invalid values
                if np.any(np.isnan(rgb_composite)) or np.any(np.isinf(rgb_composite)):
                    rgb_composite = np.nan_to_num(rgb_composite, nan=0.0, posinf=0.0, neginf=0.0)
                
                # Apply aggressive contrast stretching
                rgb_enhanced = aggressive_stretch(rgb_composite)
                
                # Create PIL image and resize
                img = Image.fromarray(rgb_enhanced)
                img = img.resize(target_size, Image.Resampling.LANCZOS)
                
                # Save as PNG with optimization
                img.save(output_path, 'PNG', optimize=True, compress_level=6)
                return True
            else:
                print(f"⚠️  Insufficient bands: {tiff_path}")
                return False
                
    except Exception as e:
        print(f"❌ Error processing {tiff_path}: {e}")
        return False

def parse_date_from_path(folder_path):
    """
    Parse date from imgs_24_25 folder structure
    Format: imgs_24_25/Month/DayMonth/
    """
    parts = Path(folder_path).parts
    
    month_name = None
    day_month = None
    
    for part in parts:
        if part in ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'March', 'April']:
            month_name = part
        elif re.match(r'\d+\w+', part):  # Pattern like "11Oct", "28Nov", etc.
            day_month = part
    
    if not month_name or not day_month:
        return None
    
    # Extract day from day_month (e.g., "11Oct" -> 11)
    day_match = re.match(r'(\d+)', day_month)
    if not day_match:
        return None
    
    day = int(day_match.group(1))
    
    # Month mapping
    month_map = {
        'Oct': 10, 'Nov': 11, 'Dec': 12,
        'Jan': 1, 'Feb': 2, 'March': 3, 'April': 4
    }
    
    month = month_map.get(month_name)
    if not month:
        return None
    
    # Determine year based on month
    if month >= 10:  # Oct, Nov, Dec
        year = 2024
    else:  # Jan, Feb, March, April
        year = 2025
    
    return (year, month, day)

def get_temporal_images_from_imgs_24_25(imgs_24_25_dir):
    """
    Scan imgs_24_25 directory and get all temporal images
    """
    temporal_images = []
    
    for root, dirs, files in os.walk(imgs_24_25_dir):
        for file in files:
            if file.endswith('.tif') and not file.endswith('_udm2.tif'):
                file_path = os.path.join(root, file)
                
                # Parse date from folder path
                date_tuple = parse_date_from_path(root)
                
                if date_tuple:
                    year, month, day = date_tuple
                    
                    # Create consistent naming: YYYY_MM_DD.png
                    png_name = f"{year:04d}_{month:02d}_{day:02d}.png"
                    
                    temporal_images.append((date_tuple, file_path, png_name))
    
    return temporal_images

def create_png_dataset_from_temporal(imgs_24_25_dir, output_dir, limit_farms=None):
    """
    Create PNG dataset from imgs_24_25 temporal images with proper naming
    """
    print("🖼️  PNG Dataset Creator (Temporal Images)")
    print("=" * 60)
    print(f"📁 Source: {imgs_24_25_dir}")
    print(f"📤 Output: {output_dir}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Get temporal images
    print("\n🔍 Scanning temporal images...")
    temporal_images = get_temporal_images_from_imgs_24_25(imgs_24_25_dir)
    
    if not temporal_images:
        print("❌ No temporal images found!")
        return
    
    # Sort by date
    temporal_images.sort(key=lambda x: x[0])
    
    print(f"📊 Found {len(temporal_images)} temporal images:")
    for date_tuple, file_path, png_name in temporal_images[:5]:  # Show first 5
        year, month, day = date_tuple
        print(f"  📅 {year}-{month:02d}-{day:02d}: {png_name}")
    if len(temporal_images) > 5:
        print(f"  ... and {len(temporal_images) - 5} more")
    
    # Get existing farm IDs
    existing_farms = []
    farm_dataset_dir = os.path.join(os.path.dirname(imgs_24_25_dir), "farm_dataset")
    
    if os.path.exists(farm_dataset_dir):
        existing_farms = [d for d in os.listdir(farm_dataset_dir) 
                         if os.path.isdir(os.path.join(farm_dataset_dir, d)) 
                         and d != "0"]
        existing_farms.sort()
        
        if limit_farms:
            existing_farms = existing_farms[:limit_farms]
            print(f"🔢 Processing first {limit_farms} farms for testing")
    
    if not existing_farms:
        print("❌ No existing farms found!")
        return
    
    print(f"🏠 Processing {len(existing_farms)} farms")
    
    total_converted = 0
    
    # Process each farm
    for i, farm_id in enumerate(existing_farms):
        farm_output_dir = os.path.join(output_dir, farm_id)
        os.makedirs(farm_output_dir, exist_ok=True)
        
        print(f"\n🏠 Processing Farm {farm_id} ({i+1}/{len(existing_farms)})")
        
        farm_converted = 0
        
        # Convert all temporal images to PNG for this farm
        for date_tuple, tif_path, png_name in temporal_images:
            png_output_path = os.path.join(farm_output_dir, png_name)
            
            # Skip if already exists
            if os.path.exists(png_output_path):
                print(f"  ✅ Exists: {png_name}")
                continue
            
            if process_tiff_to_png(tif_path, png_output_path):
                print(f"  🔄 Converted: {png_name}")
                farm_converted += 1
                total_converted += 1
            else:
                print(f"  ❌ Failed: {png_name}")
        
        print(f"  📊 Farm {farm_id}: {farm_converted} images converted")
    
    print(f"\n✅ PNG Dataset creation completed!")
    print(f"🏠 Farms processed: {len(existing_farms)}")
    print(f"🖼️  Total images per farm: {len(temporal_images)}")
    print(f"🔄 Total conversions: {total_converted}")
    print(f"📁 Output location: {output_dir}")
    
    # Benefits summary
    print(f"\n💾 Benefits:")
    print(f"   🚀 Faster web loading (PNG vs TIFF)")
    print(f"   📦 Smaller file sizes (~70-90% reduction)")
    print(f"   ⚡ Pre-processed contrast enhancement")
    print(f"   📅 Consistent temporal naming (YYYY_MM_DD.png)")

def create_png_dataset_from_existing(source_dir, output_dir, limit_farms=None):
    """
    Create PNG dataset from existing TIFF files (legacy mode)
    """
    print("🖼️  PNG Dataset Creator (Existing Dataset)")
    print("=" * 60)
    print(f"📁 Source: {source_dir}")
    print(f"📤 Output: {output_dir}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Get farm directories
    if not os.path.exists(source_dir):
        print(f"❌ Source directory not found: {source_dir}")
        return
    
    farm_dirs = [d for d in os.listdir(source_dir) 
                 if os.path.isdir(os.path.join(source_dir, d)) and d != "0"]
    farm_dirs.sort()
    
    # Limit farms if specified
    if limit_farms:
        farm_dirs = farm_dirs[:limit_farms]
        print(f"🔢 Processing first {limit_farms} farms for testing")
    
    print(f"🏠 Found {len(farm_dirs)} farms to process")
    
    total_images = 0
    
    for i, farm_id in enumerate(farm_dirs):
        print(f"\n🏠 Processing Farm {farm_id} ({i+1}/{len(farm_dirs)})")
        
        farm_input_dir = os.path.join(source_dir, farm_id)
        farm_output_dir = os.path.join(output_dir, farm_id)
        os.makedirs(farm_output_dir, exist_ok=True)
        
        # Get all TIFF files
        tiff_files = []
        for file in os.listdir(farm_input_dir):
            if file.lower().endswith(('.tif', '.tiff')):
                tiff_files.append(file)
        
        if not tiff_files:
            print(f"  ⚠️  No TIFF files found")
            continue
        
        print(f"  📷 Found {len(tiff_files)} images")
        
        # Process each TIFF file
        for j, tiff_file in enumerate(tiff_files):
            tiff_path = os.path.join(farm_input_dir, tiff_file)
            
            # Create PNG filename
            png_filename = tiff_file.rsplit('.', 1)[0] + '.png'
            png_path = os.path.join(farm_output_dir, png_filename)
            
            # Skip if already exists
            if os.path.exists(png_path):
                print(f"    ✅ Exists: {png_filename}")
                continue
            
            # Process TIFF to PNG
            if process_tiff_to_png(tiff_path, png_path):
                print(f"    🔄 Converted: {png_filename}")
                total_images += 1
            else:
                print(f"    ❌ Failed: {tiff_file}")
    
    print(f"\n✅ PNG Dataset creation completed!")
    print(f"🏠 Farms processed: {len(farm_dirs)}")
    print(f"🖼️  Total images converted: {total_images}")
    print(f"📁 Output location: {output_dir}")

def main():
    """
    Main function to create PNG dataset
    """
    # Configuration
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    imgs_24_25_dir = os.path.join(project_root, "imgs_24_25")
    enhanced_dir = os.path.join(project_root, "enhanced_farm_dataset")
    original_dir = os.path.join(project_root, "farm_dataset")
    png_output_dir = os.path.join(project_root, "farm_dataset_png")
    
    print("🎯 PNG Dataset Creator")
    print("=" * 40)
    
    # Priority 1: Use imgs_24_25 for temporal images (most up-to-date)
    if os.path.exists(imgs_24_25_dir):
        print("📈 Using imgs_24_25 temporal dataset (preferred)")
        create_png_dataset_from_temporal(imgs_24_25_dir, png_output_dir, limit_farms=10)
    
    # Priority 2: Use enhanced dataset if available
    elif os.path.exists(enhanced_dir):
        print("� Using enhanced dataset")
        create_png_dataset_from_existing(enhanced_dir, png_output_dir, limit_farms=10)
    
    # Priority 3: Use original dataset
    elif os.path.exists(original_dir):
        print("📋 Using original dataset")
        create_png_dataset_from_existing(original_dir, png_output_dir, limit_farms=10)
    
    else:
        print("❌ No dataset found!")
        print(f"   Checked: {imgs_24_25_dir}")
        print(f"   Checked: {enhanced_dir}")
        print(f"   Checked: {original_dir}")

if __name__ == "__main__":
    main()