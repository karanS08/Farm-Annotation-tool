#!/usr/bin/env python3

"""
Test script to verify date parsing functionality
"""

import sys
import os
sys.path.append('/media/karan/Loni SSD/karan_dev/app')

from app import parse_date_from_filename

def test_date_parsing():
    """Test the date parsing function with various filename formats"""
    
    test_cases = [
        ("Oct_2024.tif", (2024, 10, 1)),
        ("march_2025.tif", (2025, 3, 1)),
        ("5april,2025_psscene_analytic_8b_sr_udm2.tif", (2025, 4, 5)),
        ("10dec2024_psscene_analytic_8b_sr_udm2.tif", (2024, 12, 10)),
        ("April24_2025_psscene_analytic_8b_sr_udm2.tif", (2025, 4, 24)),
        ("Nov_2024.tif", (2024, 11, 1)),
        ("14dec2024_psscene.tif", (2024, 12, 14)),
        ("Jan_2025.tif", (2025, 1, 1)),
    ]
    
    print("🧪 Testing Date Parsing Function")
    print("=" * 50)
    
    for filename, expected in test_cases:
        result = parse_date_from_filename(filename)
        status = "✅" if result == expected else "❌"
        
        # Format dates for display
        year, month, day = result
        month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        if month > 0:
            if day > 0:
                date_display = f"{month_names[month]} {day}, {year}"
            else:
                date_display = f"{month_names[month]} {year}"
        else:
            date_display = f"{year}"
        
        print(f"{status} {filename:<40} → {date_display}")
        if result != expected:
            print(f"   Expected: {expected}, Got: {result}")
    
    print("\n🔍 Testing Chronological Sorting")
    print("=" * 50)
    
    # Test sorting
    filenames = [
        "5april,2025_psscene.tif",
        "Oct_2024.tif", 
        "march_2025.tif",
        "14dec2024_psscene.tif",
        "Jan_2025.tif",
        "Nov_2024.tif"
    ]
    
    print("Original order:")
    for f in filenames:
        print(f"  {f}")
    
    sorted_filenames = sorted(filenames, key=parse_date_from_filename)
    
    print("\nChronological order:")
    for f in sorted_filenames:
        date_tuple = parse_date_from_filename(f)
        year, month, day = date_tuple
        month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        if month > 0:
            if day > 0:
                date_display = f"{month_names[month]} {day}, {year}"
            else:
                date_display = f"{month_names[month]} {year}"
        else:
            date_display = f"{year}"
        
        print(f"  {f:<40} ({date_display})")

if __name__ == "__main__":
    test_date_parsing()