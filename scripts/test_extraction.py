"""
Test Script for Extracted Modules

This script performs basic tests to verify the extracted modules work correctly.
Run this after installation to check your setup.

Usage:
    python test_extraction.py
"""

import sys


def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    try:
        import ee
        print("  ✓ earthengine-api")
    except ImportError as e:
        print(f"  ✗ earthengine-api: {e}")
        return False
    
    try:
        import pandas
        print("  ✓ pandas")
    except ImportError as e:
        print(f"  ✗ pandas: {e}")
        return False
    
    try:
        import geopandas
        print("  ✓ geopandas")
    except ImportError as e:
        print(f"  ✗ geopandas: {e}")
        return False
    
    try:
        from shapely.geometry import Point, Polygon
        print("  ✓ shapely")
    except ImportError as e:
        print(f"  ✗ shapely: {e}")
        return False
    
    try:
        from dateutil.relativedelta import relativedelta
        print("  ✓ python-dateutil")
    except ImportError as e:
        print(f"  ✗ python-dateutil: {e}")
        return False
    
    return True


def test_module_imports():
    """Test that extracted modules can be imported."""
    print("\nTesting module imports...")
    
    try:
        from alert_grouping_navigator import AlertGroupingNavigator
        print("  ✓ alert_grouping_navigator")
    except ImportError as e:
        print(f"  ✗ alert_grouping_navigator: {e}")
        return False
    
    try:
        from mosaic_creator import MosaicCreator
        print("  ✓ mosaic_creator")
    except ImportError as e:
        print(f"  ✗ mosaic_creator: {e}")
        return False
    
    return True


def test_gee_initialization():
    """Test Google Earth Engine initialization."""
    print("\nTesting GEE initialization...")
    
    try:
        import ee
        ee.Initialize()
        print("  ✓ GEE initialized successfully")
        return True
    except Exception as e:
        print(f"  ✗ GEE initialization failed: {e}")
        print("  → Run 'earthengine authenticate' to fix")
        return False


def test_alert_navigator_instantiation():
    """Test AlertGroupingNavigator can be instantiated."""
    print("\nTesting AlertGroupingNavigator instantiation...")
    
    try:
        from alert_grouping_navigator import AlertGroupingNavigator
        
        # Use a public GLAD asset for testing
        navigator = AlertGroupingNavigator(
            asset_id="projects/glad/alert/UpdResult",
            pixel_size=30
        )
        print("  ✓ AlertGroupingNavigator created")
        return True
    except Exception as e:
        print(f"  ✗ Failed to create AlertGroupingNavigator: {e}")
        return False


def test_mosaic_creator_instantiation():
    """Test MosaicCreator can be instantiated."""
    print("\nTesting MosaicCreator instantiation...")
    
    try:
        from mosaic_creator import MosaicCreator
        
        creator = MosaicCreator()
        print("  ✓ MosaicCreator created")
        return True
    except Exception as e:
        print(f"  ✗ Failed to create MosaicCreator: {e}")
        return False


def test_date_conversion():
    """Test date conversion functionality."""
    print("\nTesting date conversion...")
    
    try:
        from mosaic_creator import MosaicCreator
        
        creator = MosaicCreator()
        
        # Test Julian date conversion
        result = creator.convert_julian_to_date(2023.100)
        expected = "2023-04-10"
        
        if result == expected:
            print(f"  ✓ Julian date conversion: {result}")
            return True
        else:
            print(f"  ✗ Expected {expected}, got {result}")
            return False
    except Exception as e:
        print(f"  ✗ Date conversion failed: {e}")
        return False


def test_date_calculations():
    """Test date range calculations."""
    print("\nTesting date calculations...")
    
    try:
        from mosaic_creator import MosaicCreator
        
        creator = MosaicCreator()
        
        # Test Planet dates
        planet_dates = creator.calculate_planet_dates("2023-06-15", "2023-07-20")
        if len(planet_dates) == 5:
            print(f"  ✓ Planet date calculation: {len(planet_dates)} dates")
        else:
            print(f"  ✗ Expected 5 dates, got {len(planet_dates)}")
            return False
        
        # Test Sentinel-2 dates
        s2_dates = creator.calculate_sentinel2_dates("2023-06-15", "2023-07-20")
        if len(s2_dates) == 4:
            print(f"  ✓ Sentinel-2 date calculation: {len(s2_dates)} dates")
        else:
            print(f"  ✗ Expected 4 dates, got {len(s2_dates)}")
            return False
        
        return True
    except Exception as e:
        print(f"  ✗ Date calculations failed: {e}")
        return False


def test_gee_operations():
    """Test basic GEE operations."""
    print("\nTesting GEE operations...")
    
    try:
        import ee
        from alert_grouping_navigator import AlertGroupingNavigator
        
        # Create a small test geometry
        test_geom = ee.Geometry.Point([-60, -3]).buffer(1000)
        area = test_geom.area().getInfo()
        
        if area > 0:
            print(f"  ✓ GEE geometry operations work")
            return True
        else:
            print(f"  ✗ GEE geometry returned zero area")
            return False
    except Exception as e:
        print(f"  ✗ GEE operations failed: {e}")
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("="*60)
    print("TESTING EXTRACTED MODULES")
    print("="*60)
    
    results = {
        "Imports": test_imports(),
        "Module imports": test_module_imports(),
        "GEE initialization": test_gee_initialization(),
        "AlertGroupingNavigator": test_alert_navigator_instantiation(),
        "MosaicCreator": test_mosaic_creator_instantiation(),
        "Date conversion": test_date_conversion(),
        "Date calculations": test_date_calculations(),
        "GEE operations": test_gee_operations(),
    }
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:30s} {status}")
    
    print("="*60)
    print(f"Results: {passed}/{total} tests passed")
    print("="*60)
    
    if passed == total:
        print("\n✓ All tests passed! Setup is complete.")
        print("You can now use the extracted modules.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed.")
        print("Please check the error messages above and fix issues.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
