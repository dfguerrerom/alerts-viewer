"""
Mosaic Creator Module

This module provides functionality to create satellite image mosaics 
from dates before and after a requested alert date.

Supports:
- Planet NICFI monthly mosaics
- Sentinel-2
- Landsat 8/9

Dependencies:
- ee (Google Earth Engine)
- datetime
"""

import ee
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Tuple, Optional


class MosaicCreator:
    """
    Class to create satellite image mosaics before and after alert dates.
    """
    
    def __init__(self):
        """Initialize the MosaicCreator."""
        pass
    
    # ========== Date calculation methods ==========
    
    def calculate_planet_dates(
        self, 
        initial_date: str, 
        final_date: str
    ) -> Tuple[str, str, str, str, str]:
        """
        Calculate optimal date ranges for Planet NICFI imagery.
        
        Args:
            initial_date: Initial detection date (YYYY-MM-DD)
            final_date: Final detection date (YYYY-MM-DD)
            
        Returns:
            Tuple of 5 dates:
            - before_start: 5 months before initial date
            - before_end: 1 day after initial detection month
            - after_start: First day of initial detection month
            - after_end: 1 day after 3 months from final date
            - alternate_before: 2 months before initial date
        """
        if isinstance(initial_date, str):
            initial_date = datetime.strptime(initial_date, "%Y-%m-%d")
        if isinstance(final_date, str):
            final_date = datetime.strptime(final_date, "%Y-%m-%d")
        
        # First day of initial detection date month
        first_day_current_month = initial_date.replace(day=1)
        
        # Second day of the next month from initial detection date
        next_month = (
            first_day_current_month + relativedelta(months=+1) + relativedelta(days=+1)
        )
        
        # First day of 5 months before
        prev_month5 = first_day_current_month + relativedelta(months=-5)
        
        # First day of final detection date month
        first_day_current_month2 = final_date.replace(day=1)
        
        # Second day of 3 months after last detection date
        next_3month = (
            first_day_current_month2 + relativedelta(months=3) + relativedelta(days=+1)
        )
        
        # First day of 2 months before first detection date
        prev_2month = first_day_current_month + relativedelta(months=-2)
        
        return (
            prev_month5.strftime("%Y-%m-%d"),
            next_month.strftime("%Y-%m-%d"),
            first_day_current_month.strftime("%Y-%m-%d"),
            next_3month.strftime("%Y-%m-%d"),
            prev_2month.strftime("%Y-%m-%d"),
        )
    
    def calculate_sentinel2_dates(
        self,
        initial_date: str,
        final_date: str
    ) -> Tuple[str, str, str, str]:
        """
        Calculate optimal date ranges for Sentinel-2 imagery.
        
        Args:
            initial_date: Initial detection date (YYYY-MM-DD)
            final_date: Final detection date (YYYY-MM-DD)
            
        Returns:
            Tuple of 4 dates:
            - before_start: 3 months before initial date
            - before_end: Initial detection date
            - after_start: 1 month before final date
            - after_end: 2 months after final date
        """
        if isinstance(initial_date, str):
            initial_date = datetime.strptime(initial_date, "%Y-%m-%d")
        if isinstance(final_date, str):
            final_date = datetime.strptime(final_date, "%Y-%m-%d")
        
        # First day of initial detection date month
        first_day_current_month = initial_date.replace(day=1)
        
        # Second day of the next month from initial detection date
        next_month = (
            first_day_current_month + relativedelta(months=+1) + relativedelta(days=+1)
        )
        
        # First day of 3 months before
        prev_month3 = first_day_current_month + relativedelta(months=-3)
        
        # First day of final detection date month
        first_day_current_month2 = final_date.replace(day=1)
        
        # Second day of 2 months after last detection date
        next_2month = (
            first_day_current_month2 + relativedelta(months=2) + relativedelta(days=+1)
        )
        
        # First day of 1 month before final detection date
        prev_1month = first_day_current_month2 + relativedelta(months=-1)
        
        return (
            prev_month3.strftime("%Y-%m-%d"),
            initial_date.strftime("%Y-%m-%d"),
            prev_1month.strftime("%Y-%m-%d"),
            next_2month.strftime("%Y-%m-%d"),
        )
    
    # ========== Image availability methods ==========
    
    def get_planet_monthly_images(
        self,
        geometry: ee.Geometry,
        date_start: str,
        date_end: str
    ) -> List[Dict]:
        """
        Get available Planet NICFI monthly images for given geometry and dates.
        
        Args:
            geometry: Area of interest as ee.Geometry
            date_start: Start date (YYYY-MM-DD)
            date_end: End date (YYYY-MM-DD)
            
        Returns:
            List of dictionaries with image information:
            - value: Display name
            - image_id: GEE asset ID
            - milis: Timestamp in milliseconds
            - source: "Planet NICFI"
            - cloud_cover: "Not available"
        """
        # Check access to Planet collections
        collections = {
            "americas": "projects/planet-nicfi/assets/basemaps/americas",
            "africa": "projects/planet-nicfi/assets/basemaps/africa",
            "asia": "projects/planet-nicfi/assets/basemaps/asia",
        }
        
        access_status = self._check_planet_collection_access(collections)
        
        if all(status == "no_access" for status in access_status.values()):
            return [{
                "value": "Not available",
                "image_id": "Not available",
                "milis": "Not available",
                "source": "Planet NICFI",
                "cloud_cover": "Not available",
            }]
        
        # Merge accessible collections
        intersecting_images = ee.ImageCollection([])
        
        for region, status in access_status.items():
            if status == "has_access":
                try:
                    img_collection = ee.ImageCollection(collections[region])
                    
                    # Check intersection with geometry
                    intersects = ee.Algorithms.If(
                        img_collection.first().geometry().intersects(geometry, 10),
                        img_collection,
                        ee.ImageCollection([])
                    )
                    intersecting_images = intersecting_images.merge(intersects)
                except ee.ee_exception.EEException:
                    continue
        
        if intersecting_images.size().getInfo() == 0:
            return [{
                "value": "Not available",
                "image_id": "Not available",
                "milis": "Not available",
                "source": "Planet NICFI",
                "cloud_cover": "Not available",
            }]
        
        # Filter by date and bounds
        planet_filtered = intersecting_images.filterDate(
            date_start, date_end
        ).filterBounds(geometry)
        
        image_ids = planet_filtered.aggregate_array("system:id").getInfo()
        elements = []
        
        for image_id in image_ids:
            parts = image_id.split("/")
            region_part = parts[-2].title()
            date_part = parts[-1].split("_")[-2]
            
            date_str = date_part + "-01"
            date_str2 = datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %Y")
            
            name = f"Planet Monthly {region_part} {date_str2}"
            planet_img = ee.Image(image_id)
            
            t2 = ee.Number(planet_img.get("system:time_end"))
            t3 = ee.Date(t2).advance(-1, "days").millis().getInfo()
            
            elements.append({
                "value": name,
                "image_id": image_id,
                "milis": t3,
                "source": "Planet NICFI",
                "cloud_cover": "Not available",
            })
        
        return elements if elements else [{
            "value": "Not available",
            "image_id": "Not available",
            "milis": "Not available",
            "source": "Planet NICFI",
            "cloud_cover": "Not available",
        }]
    
    def get_sentinel2_images(
        self,
        geometry: ee.Geometry,
        date_start: str,
        date_end: str,
        max_cloud_cover: float = 90
    ) -> List[Dict]:
        """
        Get available Sentinel-2 images for given geometry and dates.
        
        Args:
            geometry: Area of interest as ee.Geometry
            date_start: Start date (YYYY-MM-DD)
            date_end: End date (YYYY-MM-DD)
            max_cloud_cover: Maximum cloud cover percentage (default: 90)
            
        Returns:
            List of dictionaries with image information
        """
        s2 = ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
        s2_filtered = (
            s2.filterDate(date_start, date_end)
            .filterBounds(geometry)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_cover))
        )
        
        # Get unique generation times
        s2_dates_list = s2_filtered.aggregate_array("GENERATION_TIME").distinct().getInfo()
        elements = []
        
        for s2_date in s2_dates_list:
            s2_same_date = s2_filtered.filter(ee.Filter.eq("GENERATION_TIME", s2_date))
            
            mean_cloud = (
                s2_same_date.aggregate_mean("CLOUDY_PIXEL_PERCENTAGE")
                .format("%.2f")
                .getInfo()
            )
            date = datetime.fromtimestamp(s2_date / 1000).strftime("%Y-%m-%d")
            name = f"Sentinel 2 {date}"
            
            elements.append({
                "value": name,
                "image_id": s2_date,
                "milis": s2_date,
                "source": "Sentinel 2",
                "cloud_cover": mean_cloud,
            })
        
        return elements
    
    def get_landsat_images(
        self,
        geometry: ee.Geometry,
        date_start: str,
        date_end: str,
        max_cloud_cover: float = 90
    ) -> List[Dict]:
        """
        Get available Landsat 8/9 images for given geometry and dates.
        
        Args:
            geometry: Area of interest as ee.Geometry
            date_start: Start date (YYYY-MM-DD)
            date_end: End date (YYYY-MM-DD)
            max_cloud_cover: Maximum cloud cover percentage (default: 90)
            
        Returns:
            List of dictionaries with image information
        """
        l8 = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        l9 = ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
        landsat = l8.merge(l9)
        
        landsat_filtered = (
            landsat.filterDate(date_start, date_end)
            .filterBounds(geometry)
            .filter(ee.Filter.lt("CLOUD_COVER", max_cloud_cover))
        )
        
        landsat_dates_list = (
            landsat_filtered.aggregate_array("DATE_PRODUCT_GENERATED")
            .distinct()
            .getInfo()
        )
        elements = []
        
        for landsat_date in landsat_dates_list:
            landsat_img = landsat_filtered.filter(
                ee.Filter.eq("DATE_PRODUCT_GENERATED", landsat_date)
            ).first()
            
            cloud_cover = ee.Number(landsat_img.get("CLOUD_COVER")).format("%.2f").getInfo()
            scene_id = landsat_img.get("LANDSAT_SCENE_ID").getInfo()
            date = datetime.fromtimestamp(landsat_date / 1000).strftime("%Y-%m-%d")
            name = f"Landsat {date}"
            
            elements.append({
                "value": name,
                "image_id": scene_id,
                "milis": landsat_date,
                "source": "Landsat",
                "cloud_cover": cloud_cover,
            })
        
        return elements if elements else [{
            "value": "Not available",
            "image_id": "Not available",
            "milis": "Not available",
            "source": "Landsat",
            "cloud_cover": "Not available",
        }]
    
    # ========== Image retrieval methods ==========
    
    def get_mosaic_images_for_alert(
        self,
        geometry: ee.Geometry,
        alert_start_date: str,
        alert_end_date: str,
        source: str = "planet"
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Get before and after images for an alert.
        
        Args:
            geometry: Alert area geometry
            alert_start_date: Start date of alert (YYYY-MM-DD)
            alert_end_date: End date of alert (YYYY-MM-DD)
            source: Image source ("planet", "sentinel2", or "landsat")
            
        Returns:
            Tuple of (before_images, after_images) lists
        """
        if source.lower() == "planet":
            dates = self.calculate_planet_dates(alert_start_date, alert_end_date)
            before_images = self.get_planet_monthly_images(
                geometry, dates[0], dates[1]
            )
            after_images = self.get_planet_monthly_images(
                geometry, dates[2], dates[3]
            )
        elif source.lower() == "sentinel2":
            dates = self.calculate_sentinel2_dates(alert_start_date, alert_end_date)
            before_images = self.get_sentinel2_images(
                geometry, dates[0], dates[1]
            )
            after_images = self.get_sentinel2_images(
                geometry, dates[2], dates[3]
            )
        elif source.lower() == "landsat":
            dates = self.calculate_sentinel2_dates(alert_start_date, alert_end_date)
            before_images = self.get_landsat_images(
                geometry, dates[0], dates[1]
            )
            after_images = self.get_landsat_images(
                geometry, dates[2], dates[3]
            )
        else:
            raise ValueError(f"Unsupported source: {source}")
        
        return before_images, after_images
    
    def create_composite_mosaic(
        self,
        image_collection: ee.ImageCollection,
        geometry: ee.Geometry,
        bands: Optional[List[str]] = None
    ) -> ee.Image:
        """
        Create a composite mosaic from an image collection.
        
        Args:
            image_collection: Input image collection
            geometry: Area to clip to
            bands: Optional list of bands to select
            
        Returns:
            Composite ee.Image
        """
        if bands:
            image_collection = image_collection.select(bands)
        
        mosaic = image_collection.mosaic().clip(geometry)
        return mosaic
    
    # ========== Helper methods ==========
    
    def _check_planet_collection_access(self, collections: Dict[str, str]) -> Dict[str, str]:
        """
        Check access status for Planet NICFI collections.
        
        Args:
            collections: Dictionary of region names to collection paths
            
        Returns:
            Dictionary mapping regions to access status
        """
        access_status = {}
        
        for region, collection in collections.items():
            try:
                img_collection = ee.ImageCollection(collection)
                size = img_collection.size().getInfo()
                
                if size > 0:
                    access_status[region] = "has_access"
                else:
                    access_status[region] = "no_access"
            except ee.ee_exception.EEException as e:
                if "not found" in str(e):
                    access_status[region] = "no_access"
                else:
                    raise
        
        return access_status
    
    def convert_julian_to_date(self, julian_date: float) -> str:
        """
        Convert Julian date format (YYYY.DDD) to YYYY-MM-DD.
        
        Args:
            julian_date: Julian date as float
            
        Returns:
            Date string in YYYY-MM-DD format
        """
        julian_date_str = "%.3f" % julian_date
        year_str, julian_str = julian_date_str.split(".")
        year = int(year_str)
        
        date = datetime(year, 1, 1) + timedelta(days=int(julian_str) - 1)
        return date.strftime("%Y-%m-%d")
    
    # ========== Image scaling methods ==========
    
    def scale_planet_image(self, image: ee.Image) -> ee.Image:
        """Scale Planet NICFI image for visualization."""
        rgb = image.select(["B", "G", "R"])
        nir = image.select(["N"])
        
        expression1 = "min(2540, rgb) / 10"
        expression2 = "min(2540, nir / 3.937) / 10"
        
        rgb_rscl = rgb.expression(expression1, {"rgb": rgb}).toUint8()
        nir_rscl = (
            nir.expression(expression2, {"nir": nir})
            .toUint8()
            .select(["constant"], ["N"])
        )
        
        return rgb_rscl.addBands(nir_rscl)
    
    def scale_sentinel2_image(self, image: ee.Image) -> ee.Image:
        """Scale Sentinel-2 image for visualization."""
        image = image.select(["B2", "B3", "B4", "B8"], ["B", "G", "R", "N"])
        
        band1 = image.select("B").subtract(100).multiply(0.7)
        band2 = image.select("G").multiply(0.6)
        band3 = image.select("R").multiply(0.8)
        band4 = image.select("N").add(600).multiply(0.85)
        
        image_adj = band1.addBands(band2).addBands(band3).addBands(band4)
        rgb = image_adj.select(["B", "G", "R"])
        nir = image_adj.select(["N"])
        
        expression1 = "min(2540, rgb) / 10"
        expression2 = "min(2540, nir / 3.937) / 10"
        
        rgb_rscl = rgb.expression(expression1, {"rgb": rgb}).toUint8()
        nir_rscl = (
            nir.expression(expression2, {"nir": nir})
            .toUint8()
            .select(["constant"], ["N"])
        )
        
        return rgb_rscl.addBands(nir_rscl)
    
    def harmonize_landsat_to_sentinel2(self, oli_image: ee.Image) -> ee.Image:
        """
        Harmonize Landsat 8/9 OLI to Sentinel-2 reflectance scale.
        
        Args:
            oli_image: Landsat OLI image
            
        Returns:
            Harmonized ee.Image
        """
        # Convert raw DN to float reflectance
        refl = (
            oli_image.select(
                ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"],
                ["B1", "B2", "B3", "B4", "B8", "B6", "B7"],
            )
            .multiply(0.0000275)
            .add(-0.2)
        )
        
        # Coefficients from HLS v2.0 Table 5
        slopes = ee.Image.constant([0.9959, 0.9778, 1.0053, 0.9765, 0.9983, 0.9987, 1.003])
        itcps = ee.Image.constant([-0.0002, -0.0040, -0.0009, 0.0009, -0.0001, -0.0011, -0.0012])
        
        # Apply transformation
        s2_refl = refl.subtract(itcps).divide(slopes)
        
        # Convert back to 0-10000 DN scale
        s2_dn = s2_refl.multiply(10000).toShort()
        
        return ee.Image(s2_dn).copyProperties(oli_image)


# Example usage
if __name__ == "__main__":
    # Initialize Earth Engine
    ee.Initialize()
    
    # Create mosaic creator
    creator = MosaicCreator()
    
    # Example: Get images for an alert
    alert_geometry = ee.Geometry.Point([-74.1, -9.9]).buffer(1000)
    alert_start = "2023-06-15"
    alert_end = "2023-07-20"
    
    # Get Planet NICFI images
    before_imgs, after_imgs = creator.get_mosaic_images_for_alert(
        geometry=alert_geometry,
        alert_start_date=alert_start,
        alert_end_date=alert_end,
        source="planet"
    )
    
    print("Before images:")
    for img in before_imgs:
        print(f"  {img['value']}")
    
    print("\nAfter images:")
    for img in after_imgs:
        print(f"  {img['value']}")
    
    # Get Sentinel-2 images
    s2_before, s2_after = creator.get_mosaic_images_for_alert(
        geometry=alert_geometry,
        alert_start_date=alert_start,
        alert_end_date=alert_end,
        source="sentinel2"
    )
    
    print(f"\nFound {len(s2_before)} Sentinel-2 before images")
    print(f"Found {len(s2_after)} Sentinel-2 after images")
