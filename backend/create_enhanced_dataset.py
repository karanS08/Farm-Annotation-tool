#!/usr/bin/env python3
"""
Enhanced Farm Dataset Creator
Creates a comprehensive dataset from imgs_24_25 with finer temporal resolution
Now properly extracts farm thumbnails from big TIFF files using plant.csv coordinates
"""

import os
import shutil
import argparse
import rasterio
from rasterio.mask import mask
from rasterio.warp import transform_geom
from rasterio.crs import CRS
from shapely.geometry import Polygon, mapping
import pandas as pd
from datetime import datetime
import re
from pathlib import Path
import numpy as np
from PIL import Image
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

def load_farm_coordinates(csv_file):
    """
    Load farm coordinates from plant.csv
    Returns a dictionary with farm_id as key and polygon as value
    """
    try:
        df = pd.read_csv(csv_file, dtype=str)
        farm_polygons = {}

        # Detect farm id column
        possible_id_cols = ['farm_id', 'Farm Code', 'Farm_Code', 'FarmCode', 'FarmCode', 'FarmCode ']
        farm_id_col = None
        for c in df.columns:
            if c.lower() in [x.lower() for x in possible_id_cols]:
                farm_id_col = c
                break
        # Fallback heuristics: look for column that contains 'farm' or 'code'
        if not farm_id_col:
            for c in df.columns:
                if 'farm' in c.lower() and ('code' in c.lower() or 'id' in c.lower() or 'code' in c.lower()):
                    farm_id_col = c
                    break
        # If still not found, pick first numeric-like column
        if not farm_id_col:
            for c in df.columns:
                sample = df[c].dropna().head(1)
                if not sample.empty and sample.iloc[0].isdigit():
                    farm_id_col = c
                    break

        # Coordinate column detection
        lat_cols = ['Lang1', 'Lat1', 'LAT1', 'lang1']
        lon_cols = ['Long1', 'Lon1', 'LON1', 'long1']
        lat_col = next((c for c in df.columns if c in lat_cols), None)
        lon_col = next((c for c in df.columns if c in lon_cols), None)

        # WKT fallback
        wkt_col = next((c for c in df.columns if c.upper() == 'WKT' or c.lower() == 'wkt'), None)

        for _, row in df.iterrows():
            # Determine farm id
            if farm_id_col and pd.notna(row.get(farm_id_col)):
                farm_id = str(row.get(farm_id_col)).strip()
            else:
                # fallback to index-based id
                farm_id = str(_)

            try:
                if wkt_col and pd.notna(row.get(wkt_col)):
                    # Use WKT geometry if present
                    try:
                        from shapely import wkt
                        poly = wkt.loads(row.get(wkt_col))
                    except Exception:
                        # If shapely.wkt not available, skip
                        thread_safe_print(f"⚠️  Skipping farm {farm_id}: invalid WKT")
                        continue
                elif lat_col and lon_col and pd.notna(row.get(lat_col)) and pd.notna(row.get(lon_col)):
                    # Use simple 4-point Lang/Long columns
                    try:
                        coords = [
                            (float(row.get(lon_col)), float(row.get(lat_col))),
                            (float(row.get(lon_col.replace('1','2'))), float(row.get(lat_col.replace('1','2')))),
                            (float(row.get(lon_col.replace('1','3'))), float(row.get(lat_col.replace('1','3')))),
                            (float(row.get(lon_col.replace('1','4'))), float(row.get(lat_col.replace('1','4')))),
                            (float(row.get(lon_col)), float(row.get(lat_col)))
                        ]
                        poly = Polygon(coords)
                    except Exception as e:
                        thread_safe_print(f"⚠️  Skipping farm {farm_id}: Invalid coordinates: {e}")
                        continue
                else:
                    # No usable coordinates
                    thread_safe_print(f"⚠️  Skipping farm {farm_id}: missing coordinate columns")
                    continue

                # Add small buffer (approx ~5 meters in degrees)
                buffered_poly = poly.buffer(0.000045)
                farm_polygons[farm_id] = buffered_poly
            except Exception as e:
                thread_safe_print(f"⚠️  Skipping farm {farm_id}: {e}")
                continue

        thread_safe_print(f"📍 Loaded {len(farm_polygons)} farm coordinates from CSV")
        return farm_polygons
        
    except Exception as e:
        thread_safe_print(f"❌ Error loading farm coordinates: {e}")
        return {}

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

def extract_farm_thumbnail(src_path, farm_id, farm_polygon, output_path, save_as_png=True, target_size=(500, 500)):
    """
    Extract a single farm thumbnail from a big TIFF file
    """
    try:
        with rasterio.open(src_path) as src:
            # Transform polygon from WGS84 to the TIFF's CRS
            src_crs = CRS.from_epsg(4326)  # WGS84 (lat/lon)
            dst_crs = src.crs  # TIFF's CRS
            
            # Transform the geometry
            farm_geom = mapping(farm_polygon)
            transformed_geom = transform_geom(src_crs, dst_crs, farm_geom)
            
            # Convert back to polygon for masking
            geojson_geom = [transformed_geom]
            
            # Extract the farm area
            out_image, out_transform = mask(src, geojson_geom, crop=True)
            
            if save_as_png and out_image.shape[0] >= 4:
                # Convert to RGB PNG with enhanced contrast
                rgb_composite = np.stack([out_image[3], out_image[2], out_image[1]], axis=-1)
                
                # Handle invalid values
                if np.any(np.isnan(rgb_composite)) or np.any(np.isinf(rgb_composite)):
                    rgb_composite = np.nan_to_num(rgb_composite, nan=0.0, posinf=0.0, neginf=0.0)
                
                # Apply aggressive contrast stretching
                rgb_enhanced = aggressive_stretch(rgb_composite)
                
                # Create PIL image and resize
                img = Image.fromarray(rgb_enhanced)
                img = img.resize(target_size, Image.Resampling.LANCZOS)
                
                # Change extension to .png
                png_output_path = os.path.splitext(output_path)[0] + '.png'
                img.save(png_output_path, format='PNG', optimize=True)
                return png_output_path
            else:
                # Save as TIFF
                out_meta = src.meta.copy()
                out_meta.update({
                    "driver": "GTiff",
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform,
                    "compress": "lzw"
                })
                
                with rasterio.open(output_path, "w", **out_meta) as dest:
                    dest.write(out_image)
                return output_path
                
    except Exception as e:
        thread_safe_print(f"❌ Failed to extract farm {farm_id} from {src_path}: {e}")
        return None

def parse_date_from_path(folder_path):
    """
    Parse date information from folder structure
    Expected format: imgs_24_25/Month/DayMonth/
    e.g., imgs_24_25/Oct/11Oct/ -> (2024, 10, 11)
         imgs_24_25/Nov/28Nov/ -> (2024, 11, 28)
         imgs_24_25/March/12Mar/ -> (2025, 3, 12)
         imgs_24_25/April/24Apr/ -> (2025, 4, 24)
    """
    parts = Path(folder_path).parts
    
    # Find month and day from path
    month_name = None
    day_month = None
    
    for part in parts:
        if part in ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'March', 'April']:
            month_name = part
        elif part.endswith(('Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr')):
            day_month = part
    
    if not month_name or not day_month:
        return None
    
    # Extract day from day_month (e.g., "11Oct" -> 11, "12Mar" -> 12)
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
    """
    Parse date information from folder structure
    Expected format: imgs_24_25/Month/DayMonth/
    e.g., imgs_24_25/Oct/11Oct/ -> (2024, 10, 11)
         imgs_24_25/Nov/28Nov/ -> (2024, 11, 28)
    """
    parts = Path(folder_path).parts
    
    # Find month and day from path
    month_name = None
    day_month = None
    
    for part in parts:
        if part in ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'March', 'April']:
            month_name = part
        elif part.endswith(('Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'March', 'April')):
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

def get_temporal_tiff_files(imgs_24_25_dir):
    """
    Scan the imgs_24_25 directory and find all TIFF files with proper date parsing
    Returns a list of tuples: (date_tuple, file_path, date_name)
    """
    tiff_files = []
    
    for root, dirs, files in os.walk(imgs_24_25_dir):
        for file in files:
            if file.endswith('.tif') and not file.endswith('_udm2.tif'):
                file_path = os.path.join(root, file)
                
                # Parse date from folder path
                date_tuple = parse_date_from_path(root)
                
                if date_tuple:
                    year, month, day = date_tuple
                    # Create consistent date naming
                    date_name = f"{year:04d}_{month:02d}_{day:02d}"
                    tiff_files.append((date_tuple, file_path, date_name))
                    thread_safe_print(f"📅 Found: {date_name} -> {file_path}")
    
    return tiff_files

def process_single_farm_temporal(args):
    """Process a single farm across all temporal images"""
    farm_id, farm_polygon, temporal_files, output_dir, save_as_png = args
    
    try:
        # Create output directory for this farm
        # Some input CSVs append a suffix like `_1` or `_2` to farm_id (from plot numbers).
        # For folder names we want the canonical farm id only (strip trailing _<number>).
        folder_name = re.sub(r'_[0-9]+$', '', str(farm_id))
        farm_output_dir = os.path.join(output_dir, folder_name)
        os.makedirs(farm_output_dir, exist_ok=True)
        
        images_processed = 0
        
        # Process each temporal image for this farm
        for date_tuple, tiff_path, date_name in temporal_files:
            ext = '.png' if save_as_png else '.tif'
            output_path = os.path.join(farm_output_dir, f"{date_name}{ext}")
            
            # Skip if already exists
            if os.path.exists(output_path):
                continue
            
            # Extract farm thumbnail
            result_path = extract_farm_thumbnail(
                tiff_path, farm_id, farm_polygon, output_path, save_as_png
            )
            
            if result_path:
                images_processed += 1
        
        update_progress()
        return f"Farm {farm_id}: {images_processed} images processed"
        
    except Exception as e:
        update_progress()
        return f"Farm {farm_id}: ERROR - {e}"

def create_enhanced_dataset(imgs_24_25_dir, plant_csv_file, output_dir, save_as_png=True, max_workers=4):
    """
    Create enhanced dataset by extracting farm thumbnails from temporal big TIFF files
    """
    global total_farms, completed_farms
    
    thread_safe_print("� Enhanced Farm Dataset Creator v2.0")
    thread_safe_print("=" * 60)
    thread_safe_print(f"📁 Source images: {imgs_24_25_dir}")
    thread_safe_print(f"� Farm coordinates: {plant_csv_file}")
    thread_safe_print(f"📤 Output directory: {output_dir}")
    thread_safe_print(f"🖼️  Output format: {'PNG' if save_as_png else 'TIFF'}")
    thread_safe_print(f"🧵 Workers: {max_workers}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Load farm coordinates from plant.csv
    thread_safe_print("\n📍 Loading farm coordinates...")
    farm_polygons = load_farm_coordinates(plant_csv_file)
    if not farm_polygons:
        thread_safe_print("❌ No valid farm coordinates found!")
        return
    
    # Find all temporal TIFF files
    thread_safe_print("\n🔍 Scanning temporal TIFF files...")
    temporal_files = get_temporal_tiff_files(imgs_24_25_dir)
    
    if not temporal_files:
        thread_safe_print("❌ No temporal TIFF files found!")
        return
    
    # Sort by date
    temporal_files.sort(key=lambda x: x[0])
    
    thread_safe_print(f"📊 Found {len(temporal_files)} temporal images:")
    for date_tuple, file_path, date_name in temporal_files[:5]:  # Show first 5
        year, month, day = date_tuple
        thread_safe_print(f"  📅 {year}-{month:02d}-{day:02d}: {date_name}")
    if len(temporal_files) > 5:
        thread_safe_print(f"  ... and {len(temporal_files) - 5} more")
    
    # Prepare arguments for parallel processing
    total_farms = len(farm_polygons)
    completed_farms = 0
    
    thread_safe_print(f"\n🏠 Processing {total_farms} farms with {len(temporal_files)} temporal images each...")
    
    farm_args = []
    for farm_id, farm_polygon in farm_polygons.items():
        farm_args.append((farm_id, farm_polygon, temporal_files, output_dir, save_as_png))
    
    # Process farms in parallel
    start_time = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_farm = {executor.submit(process_single_farm_temporal, args): args[0] 
                         for args in farm_args}
        
        for future in as_completed(future_to_farm):
            farm_id = future_to_farm[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                thread_safe_print(f"❌ Farm {farm_id} failed: {e}")
                update_progress()
    
    end_time = time.time()
    
    thread_safe_print(f"\n✅ Enhanced dataset creation completed!")
    thread_safe_print(f"⏱️  Total time: {end_time - start_time:.2f} seconds")
    thread_safe_print(f"📁 Output: {output_dir}")
    thread_safe_print(f"🏠 Farms processed: {total_farms}")
    thread_safe_print(f"📷 Images per farm: {len(temporal_files)}")
    thread_safe_print(f"🖼️  Format: {'PNG (optimized for web)' if save_as_png else 'TIFF (original quality)'}")
    
    # Show some results
    if results:
        thread_safe_print(f"\n� Sample results:")
        for result in results[:5]:
            thread_safe_print(f"  {result}")
        if len(results) > 5:
            thread_safe_print(f"  ... and {len(results) - 5} more")

def main():
    """
    Main function to create enhanced dataset
    """
    parser = argparse.ArgumentParser(description='Create enhanced farm dataset from temporal TIFFs and a farm CSV (e.g. 40k.csv)')
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    default_csv = os.path.join(project_root, '40k.csv')
    default_imgs = os.path.join(project_root, 'imgs_24_25')
    default_out = os.path.join(project_root, 'enhanced_farm_dataset')

    parser.add_argument('--input', '-i', default=default_csv, help='Path to farm CSV (default: 40k.csv in project root)')
    parser.add_argument('--imgs', '-m', default=default_imgs, help='Path to imgs_24_25 directory')
    parser.add_argument('--output', '-o', default=default_out, help='Output directory for enhanced dataset')
    parser.add_argument('--workers', '-w', type=int, default=4, help='Number of worker threads')
    parser.add_argument('--png', action='store_true', help='Save as PNG (default behavior)')
    parser.add_argument('--no-png', dest='png', action='store_false', help='Save as TIFF instead')
    parser.set_defaults(png=True)

    args = parser.parse_args()

    imgs_24_25_dir = args.imgs
    plant_csv_file = args.input
    output_dir = args.output

    print("🎯 Enhanced Farm Dataset Creator")
    print("=" * 40)

    # Validate input directories and files
    if not os.path.exists(imgs_24_25_dir):
        print(f"❌ imgs_24_25 directory not found: {imgs_24_25_dir}")
        return

    if not os.path.exists(plant_csv_file):
        print(f"❌ farm CSV file not found: {plant_csv_file}")
        return

    # Create enhanced dataset
    print("🚀 Starting enhanced dataset creation...")
    print("📝 This will:")
    print("   1. Load farm coordinates from the provided CSV")
    print("   2. Find all temporal TIFF files in imgs_24_25/")
    print("   3. Extract farm thumbnails for each date")
    print("   4. Save as optimized PNG images (unless --no-png is used)")
    print("   5. Organize by farm ID with date-labeled files")

    create_enhanced_dataset(
        imgs_24_25_dir=imgs_24_25_dir,
        plant_csv_file=plant_csv_file,
        output_dir=output_dir,
        save_as_png=args.png,  # Save as PNG for web optimization by default
        max_workers=args.workers
    )

if __name__ == "__main__":
    main()