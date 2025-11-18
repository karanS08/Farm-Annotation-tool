import os
import hashlib
from PIL import Image
import rasterio
import numpy as np
import io
import base64

class ImageProcessor:
    def __init__(self, farm_dataset_dir, thumbnails_dir=None):
        self.farm_dataset_dir = farm_dataset_dir
        # thumbnails_dir is no longer needed since we generate on-the-fly
        
    def generate_thumbnail_base64(self, img_path, size=(500, 500)):
        """
        Generate high-resolution thumbnail in memory and return as base64 string
        Handles both TIFF (legacy) and PNG (enhanced dataset) files
        
        Args:
            img_path (str): Path to the original TIFF or PNG file
            size (tuple): Thumbnail size (width, height)
        
        Returns:
            str: Base64 encoded PNG image, or None if failed
        """
        try:
            # Check if it's a PNG file (enhanced dataset)
            if img_path.lower().endswith('.png'):
                # PNG files are already processed and optimized
                with Image.open(img_path) as img:
                    # Resize if needed
                    if img.size != size:
                        img = img.resize(size, Image.Resampling.LANCZOS)
                    
                    # Convert to base64
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG', optimize=True)
                    buffer.seek(0)
                    
                    img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
                    return f"data:image/png;base64,{img_base64}"
            
            # Legacy TIFF processing
            with rasterio.open(img_path) as src:
                bands = src.read()
                
                if bands.shape[0] >= 4:
                    # Create RGB image with:
                    # R = band 4 (Red channel)
                    # G = band 3 (Green channel) 
                    # B = band 2 (Blue channel)
                    # Band indexing: rasterio uses 0-based, so band 4=index 3, band 3=index 2, band 2=index 1
                    rgb_composite = np.stack([bands[3], bands[2], bands[1]], axis=-1)  # R, G, B
                    
                    # Check for invalid values
                    if np.any(np.isnan(rgb_composite)) or np.any(np.isinf(rgb_composite)):
                        # Replace NaN/Inf with 0
                        rgb_composite = np.nan_to_num(rgb_composite, nan=0.0, posinf=0.0, neginf=0.0)
                    
                    # Apply aggressive contrast stretching (same as test.py)
                    def aggressive_stretch(rgb_array, percentile_range=(0.5, 99.5)):
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
                    
                    # Apply the aggressive stretch
                    rgb_composite = aggressive_stretch(rgb_composite)
                    
                    # Create PIL image
                    img = Image.fromarray(rgb_composite)
                    
                    # Resize to target size (upscale if needed)
                    img = img.resize(size, Image.Resampling.LANCZOS)
                    
                    # Save to memory buffer instead of file
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG', optimize=False, compress_level=1)
                    buffer.seek(0)
                    
                    # Convert to base64 for web display
                    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    
                    return f"data:image/png;base64,{img_base64}"
                    
                else:
                    return None
                    
        except Exception as e:
            return None
    
    def cleanup_thumbnails(self, keep_farms=None):
        """
        No longer needed - thumbnails are generated on-demand and not saved
        """
        pass
    
    def get_thumbnail_stats(self):
        """Get statistics about generated thumbnails - now always zero since not saved"""
        return {'total': 0, 'size_mb': 0, 'note': 'Thumbnails generated on-demand, not saved'}