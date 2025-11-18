#!/usr/bin/env python3
"""
Debug script to visualize generated thumbnails using matplotlib
"""

import os
import sys
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from image_utils import ImageProcessor
import base64
from io import BytesIO
from PIL import Image
import numpy as np

def debug_thumbnails():
    """Generate and display thumbnails for debugging"""
    
    # Setup paths
    app_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(app_dir)
    farm_dataset_dir = os.path.join(root_dir, "farm_dataset")
    
    print("🔍 Farm Thumbnail Debug Tool")
    print("=" * 50)
    print(f"📁 Farm dataset: {farm_dataset_dir}")
    
    # Initialize image processor
    image_processor = ImageProcessor(farm_dataset_dir)
    
    # Find first few farms
    if not os.path.isdir(farm_dataset_dir):
        print(f"❌ Farm dataset directory not found: {farm_dataset_dir}")
        return
    
    farm_dirs = [d for d in os.listdir(farm_dataset_dir) 
                 if os.path.isdir(os.path.join(farm_dataset_dir, d)) and d != "0"]
    farm_dirs.sort()
    
    if not farm_dirs:
        print("❌ No farm directories found")
        return
    
    print(f"📊 Found {len(farm_dirs)} farms")
    
    # Process first farm for debugging
    farm_id = farm_dirs[0]
    farm_path = os.path.join(farm_dataset_dir, farm_id)
    
    print(f"\n🎯 Processing Farm: {farm_id}")
    print(f"📂 Path: {farm_path}")
    
    # Find TIFF files
    tiff_files = []
    for file in os.listdir(farm_path):
        if file.lower().endswith(('.tif', '.tiff')):
            tiff_files.append(os.path.join(farm_path, file))
    
    if not tiff_files:
        print("❌ No TIFF files found in farm directory")
        return
    
    print(f"📷 Found {len(tiff_files)} TIFF files")
    
    # Process first few images (max 6 for display)
    max_images = min(6, len(tiff_files))
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle(f'Thumbnail Debug - Farm {farm_id}', fontsize=16)
    
    # Flatten axes for easier indexing
    axes = axes.flatten()
    
    for i in range(max_images):
        img_path = tiff_files[i]
        filename = os.path.basename(img_path)
        
        print(f"\n🖼️  Processing: {filename}")
        print(f"   Full path: {img_path}")
        
        try:
            # Generate thumbnail as base64
            thumbnail_data_url = image_processor.generate_thumbnail_base64(img_path)
            
            # Extract base64 data
            if thumbnail_data_url.startswith('data:image/png;base64,'):
                base64_data = thumbnail_data_url.split(',')[1]
                
                # Decode base64 to image
                image_data = base64.b64decode(base64_data)
                image = Image.open(BytesIO(image_data))
                
                # Convert to numpy array for matplotlib
                img_array = np.array(image)
                
                # Display in subplot
                axes[i].imshow(img_array)
                axes[i].set_title(f'{filename}\n{img_array.shape}', fontsize=10)
                axes[i].axis('off')
                
                print(f"   ✅ Success: {img_array.shape}")
                print(f"   📏 Size: {image.size}")
                
            else:
                print(f"   ❌ Invalid data URL format")
                axes[i].text(0.5, 0.5, 'Invalid\nData URL', 
                           ha='center', va='center', transform=axes[i].transAxes)
                axes[i].axis('off')
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            axes[i].text(0.5, 0.5, f'Error:\n{str(e)[:50]}...', 
                        ha='center', va='center', transform=axes[i].transAxes)
            axes[i].axis('off')
    
    # Hide unused subplots
    for i in range(max_images, 6):
        axes[i].axis('off')
    
    plt.tight_layout()
    
    # Save debug plot
    debug_plot_path = os.path.join(app_dir, 'thumbnail_debug.png')
    plt.savefig(debug_plot_path, dpi=150, bbox_inches='tight')
    print(f"\n💾 Debug plot saved: {debug_plot_path}")
    
    # Show plot
    plt.show()
    
    print("\n📝 Debug Summary:")
    print(f"   🏠 Farm processed: {farm_id}")
    print(f"   📷 Images processed: {max_images}")
    print(f"   🖼️  RGB bands: R=Band4, G=Band3, B=Band2 (with aggressive contrast stretch)")
    print(f"   📏 Target size: 500x500 pixels")

if __name__ == "__main__":
    debug_thumbnails()