#!/usr/bin/env python3
"""
Thumbnail management utility for Farm Harvest Annotation Tool

NOTE: As of the latest version, thumbnails are generated on-demand 
and not saved to disk, so this script is no longer needed.
However, it's kept for reference and in case you want to clear 
any old thumbnail files that might exist.
"""

import os

def main():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    thumbnails_dir = os.path.join(app_dir, 'static', 'thumbnails')
    
    print("🖼️  Farm Harvest Annotation - Thumbnail Management")
    print("=" * 50)
    
    if os.path.exists(thumbnails_dir):
        # Count existing files
        thumbnail_files = [f for f in os.listdir(thumbnails_dir) if f.endswith('.png')]
        
        if thumbnail_files:
            print(f"📁 Found {len(thumbnail_files)} old thumbnail files")
            
            response = input("Do you want to remove these old files? (y/N): ")
            if response.lower() in ['y', 'yes']:
                for file in thumbnail_files:
                    file_path = os.path.join(thumbnails_dir, file)
                    os.remove(file_path)
                    print(f"🗑️  Removed: {file}")
                
                # Remove directory if empty
                try:
                    os.rmdir(thumbnails_dir)
                    print(f"📁 Removed empty directory: {thumbnails_dir}")
                except OSError:
                    print(f"📁 Directory not empty, keeping: {thumbnails_dir}")
                
                print("✅ Cleanup completed!")
            else:
                print("ℹ️  No files removed")
        else:
            print("✅ No old thumbnail files found")
    else:
        print("ℹ️  No thumbnails directory found")
    
    print("\n📝 Note: The current version generates thumbnails on-demand")
    print("   and doesn't save them to disk, so this cleanup is not")
    print("   typically needed anymore.")

if __name__ == "__main__":
    main()