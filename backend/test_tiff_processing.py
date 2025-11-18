#!/usr/bin/env python3
"""
Test TIFF image processing for the farm annotation tool.
This script verifies that TIFF files can be properly opened and converted to PNG thumbnails.
"""
import os
import sys
from PIL import Image
import numpy as np
from pathlib import Path
import rasterio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_tiff_file(tiff_path: str):
    """Test opening and processing a TIFF file."""
    print(f"\n{'='*60}")
    print(f"Testing: {os.path.basename(tiff_path)}")
    print(f"{'='*60}")
    
    if not os.path.exists(tiff_path):
        print(f"❌ File not found: {tiff_path}")
        return False
    
    try:
        # Try rasterio first for multispectral TIFFs
        with rasterio.open(tiff_path) as src:
            print(f"✓ Successfully opened TIFF with rasterio")
            print(f"  - Size: {src.width}x{src.height}")
            print(f"  - Bands: {src.count}")
            print(f"  - Data type: {src.dtypes[0]}")
            
            # Read the data
            data = src.read()
            print(f"  - Data shape: {data.shape}")
            print(f"  - Value range: {data.min()} - {data.max()}")
            
            # Handle different band counts
            if data.shape[0] >= 3:
                # Multi-band: Use first 3 bands as RGB
                if data.shape[0] >= 4:
                    # Use bands 3,2,1 (common for satellite imagery)
                    rgb = np.stack([
                        data[2, :, :],  # Red
                        data[1, :, :],  # Green
                        data[0, :, :]   # Blue
                    ], axis=-1)
                    print(f"  - Using bands 3,2,1 as RGB")
                else:
                    # 3 bands: assume RGB
                    rgb = np.stack([
                        data[0, :, :],
                        data[1, :, :],
                        data[2, :, :]
                    ], axis=-1)
                    print(f"  - Using bands 1,2,3 as RGB")
            elif data.shape[0] == 1:
                # Single band: grayscale
                rgb = data[0, :, :]
                print(f"  - Single band (grayscale)")
            else:
                raise ValueError(f"Unsupported band count: {data.shape[0]}")
            
            # Normalize to 0-255 range
            if rgb.dtype in [np.float32, np.float64]:
                rgb_min, rgb_max = rgb.min(), rgb.max()
                if rgb_max > rgb_min:
                    rgb = ((rgb - rgb_min) / (rgb_max - rgb_min) * 255).astype(np.uint8)
                else:
                    rgb = np.zeros_like(rgb, dtype=np.uint8)
                print(f"  - Normalized float data to 8-bit")
            elif rgb.dtype == np.uint16:
                rgb = (rgb / 256).astype(np.uint8)
                print(f"  - Converted 16-bit to 8-bit")
            elif rgb.dtype != np.uint8:
                rgb_min, rgb_max = rgb.min(), rgb.max()
                if rgb_max > rgb_min:
                    rgb = ((rgb.astype(np.float32) - rgb_min) / (rgb_max - rgb_min) * 255).astype(np.uint8)
                else:
                    rgb = np.zeros_like(rgb, dtype=np.uint8)
                print(f"  - Normalized {rgb.dtype} to 8-bit")
            
            # Create PIL Image
            if len(rgb.shape) == 3:
                im = Image.fromarray(rgb, mode='RGB')
                print(f"✓ Created RGB PIL Image: {im.size}")
            else:
                im = Image.fromarray(rgb, mode='L').convert('RGB')
                print(f"✓ Created grayscale->RGB PIL Image: {im.size}")
            
            # Test thumbnail creation
            im.thumbnail((300, 300), Image.LANCZOS)
            print(f"✓ Created thumbnail: {im.size}")
            
            # Test PNG save
            test_output = f"test_thumb_{Path(tiff_path).stem}.png"
            im.save(test_output, format='PNG', optimize=True)
            print(f"✓ Saved PNG thumbnail: {test_output}")
            
            # Clean up test file
            if os.path.exists(test_output):
                os.remove(test_output)
                print(f"✓ Cleaned up test file")
            
            print(f"✅ SUCCESS: TIFF processing works correctly")
            return True
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run tests on sample TIFF files from the dataset."""
    print("🧪 TIFF Processing Test Suite")
    print("="*60)
    
    # Get farm dataset directory
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    farm_dataset_dir = os.path.join(root_dir, "farm_dataset")
    
    if not os.path.exists(farm_dataset_dir):
        print(f"❌ Farm dataset directory not found: {farm_dataset_dir}")
        return
    
    print(f"📁 Scanning: {farm_dataset_dir}")
    
    # Find TIFF files
    tiff_files = []
    for root, dirs, files in os.walk(farm_dataset_dir):
        for file in files:
            if file.lower().endswith(('.tif', '.tiff')):
                tiff_files.append(os.path.join(root, file))
                if len(tiff_files) >= 3:  # Test first 3 files
                    break
        if len(tiff_files) >= 3:
            break
    
    if not tiff_files:
        print("❌ No TIFF files found in dataset")
        return
    
    print(f"Found {len(tiff_files)} TIFF file(s) to test\n")
    
    # Test each file
    results = []
    for tiff_file in tiff_files:
        result = test_tiff_file(tiff_file)
        results.append((tiff_file, result))
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 Test Summary")
    print(f"{'='*60}")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✅ All tests passed!")
    else:
        print("⚠️ Some tests failed")
        for path, result in results:
            if not result:
                print(f"  ❌ {os.path.basename(path)}")


if __name__ == "__main__":
    main()
