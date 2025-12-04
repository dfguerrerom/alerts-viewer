"""
Alert Grouping and Navigation Module

This module provides functionality to:
1. Load alerts from a GEE asset (alert raster)
2. Group alerts into bounding boxes
3. Navigate through grouped alerts

Dependencies:
- ee (Google Earth Engine)
- geopandas
- pandas
- shapely
"""

import ee
import time
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import requests
from io import BytesIO
from PIL import Image


class AlertGroupingNavigator:
    """
    Class to group and navigate through deforestation alerts from GEE assets.
    """

    def __init__(
        self,
        asset_id: Optional[str] = None,
        alert_image: Optional[ee.Image] = None,
        pixel_size: float = 30,
    ):
        """
        Initialize the AlertGroupingNavigator.

        Args:
            asset_id: Google Earth Engine asset ID containing alert raster (optional if alert_image provided)
            alert_image: ee.Image containing alert data (optional if asset_id provided)
            pixel_size: Pixel size in meters for analysis (default: 30)

        Note:
            Either asset_id or alert_image must be provided, but not both.
        """
        if asset_id is None and alert_image is None:
            raise ValueError("Either asset_id or alert_image must be provided")
        if asset_id is not None and alert_image is not None:
            raise ValueError("Cannot provide both asset_id and alert_image")

        self.asset_id = asset_id
        self.alert_image = alert_image
        self.pixel_size = pixel_size
        self.alerts_gdf = None
        self.current_index = 0

    def evaluate_with_retry(self, ee_object, max_retries: int = 5, delay: int = 3):
        """
        Evaluates a Google Earth Engine object with retry logic.

        Args:
            ee_object: The Earth Engine object to evaluate
            max_retries: Maximum number of retries if computation times out
            delay: Delay in seconds between retries

        Returns:
            The result of the computation as a JSON object

        Raises:
            Exception: If all retries fail
        """
        attempt = 0
        while attempt < max_retries:
            try:
                return ee_object.getInfo()
            except ee.ee_exception.EEException as e:
                if "Computation timed out" in str(e):
                    attempt += 1
                    print(
                        f"Attempt {attempt} failed due to timeout. Retrying in {delay} seconds..."
                    )
                    time.sleep(delay)
                else:
                    raise
        raise Exception(f"All {max_retries} attempts failed due to timeout.")

    def group_alerts(
        self,
        aoi: ee.FeatureCollection,
        min_alert_size_pixels: int = 1,
        max_alerts: int = 30,
        sorting_method: str = "largest_first",
        grid_size: int = 150000,
    ) -> gpd.GeoDataFrame:
        """
        Group alerts from the GEE asset into bounding boxes.

        Args:
            aoi: Area of Interest as ee.FeatureCollection
            min_alert_size_pixels: Minimum number of pixels for an alert cluster
            max_alerts: Maximum number of alerts to retrieve
            sorting_method: How to sort alerts. Options:
                - "largest_first": Largest areas first
                - "smallest_first": Smallest areas first
                - "newest_first": Most recent alerts first
                - "oldest_first": Oldest alerts first
            grid_size: Grid size for spatial processing (meters)

        Returns:
            GeoDataFrame with grouped alerts
        """
        # Load alert raster from asset or use provided image
        if self.alert_image is not None:
            alert_raster_raw = self.alert_image
        else:
            alert_raster_raw = ee.Image(self.asset_id)

        # Check if this is a CCDC-style alert (has detection_count band)
        band_names = alert_raster_raw.bandNames().getInfo()

        if "detection_count" in band_names:
            # This is a CCDC-style alert - convert to integer format
            print("Detected CCDC-style alert format, converting to integer bands...")

            # Create alert band from detection_count (must be integer)
            alert_band = (
                alert_raster_raw.select("detection_count")
                .unmask(0)
                .toInt16()
                .rename("alert")
            )

            # Create date band from first_detection_date
            date_band = (
                alert_raster_raw.select("first_detection_date")
                .unmask(0)
                .toFloat()
                .rename("date")
            )

            # Combine into single image
            alert_raster = alert_band.addBands(date_band)

            # Create reducer for CCDC format
            ee_reducer = (
                ee.Reducer.count()
                .combine(
                    reducer2=ee.Reducer.min().setOutputs(["alert_date_min"]),
                    sharedInputs=True,
                )
                .combine(
                    reducer2=ee.Reducer.max().setOutputs(["alert_date_max"]),
                    sharedInputs=True,
                )
            )
        else:
            # Standard multi-source alert format
            alert_raster = alert_raster_raw

            # Create reducer for extracting alert properties
            ee_reducer = (
                ee.Reducer.count()
                .combine(
                    reducer2=ee.Reducer.toList().setOutputs(["alert_type_list"]),
                    sharedInputs=True,
                )
                .combine(
                    reducer2=ee.Reducer.min().setOutputs(["alert_date_min"]),
                    sharedInputs=True,
                )
                .combine(
                    reducer2=ee.Reducer.max().setOutputs(["alert_date_max"]),
                    sharedInputs=True,
                )
            )

        # Get grouped alerts using grid-based approach
        alert_features = self._get_alerts_with_grid(
            aoi=aoi,
            alert_raster=alert_raster,
            ee_reducer=ee_reducer,
            min_alert_size_pixels=min_alert_size_pixels,
            max_alerts=max_alerts,
            sorting_method=sorting_method,
            grid_size=grid_size,
        )

        # Convert to GeoDataFrame
        self.alerts_gdf = self._convert_to_geopandas(alert_features)
        self.current_index = 0

        return self.alerts_gdf

    def _get_alerts_with_grid(
        self,
        aoi: ee.FeatureCollection,
        alert_raster: ee.Image,
        ee_reducer,
        min_alert_size_pixels: int,
        max_alerts: int,
        sorting_method: str,
        grid_size: int,
    ) -> List[Dict]:
        """
        Extract alerts using a grid-based approach for large areas.
        """

        def get_bounding_boxes(feature):
            """Extract bounding boxes for alert clusters in a grid cell."""
            grid_geometry = ee.Feature(feature).geometry()
            bounding_boxes = alert_raster.clip(grid_geometry).reduceToVectors(
                reducer=ee_reducer,
                geometry=grid_geometry,
                scale=self.pixel_size,
                geometryType="bb",
                eightConnected=True,
                maxPixels=1e13,
            )

            # Filter clusters with at least min_alert_size_pixels
            bb_cleaned = bounding_boxes.filter(
                ee.Filter.gte("count", min_alert_size_pixels)
            )
            return bb_cleaned

        def process_grid_element(element):
            """Process each grid element."""
            bb = get_bounding_boxes(element)
            count = bb.size()
            return ee.Algorithms.If(count.gte(1), bb, ee.FeatureCollection([]))

        def apply_distinct(fc, property_name: str, new_property_name: str):
            """Apply distinct to a list property in each feature."""
            # Check if collection is empty
            fc_size = fc.size().getInfo()
            if fc_size == 0:
                return fc

            # Check if property exists in features
            first_feature = ee.Feature(fc.first())
            props = first_feature.propertyNames().getInfo()

            if property_name not in props:
                # Property doesn't exist (CCDC format), return as-is
                return fc

            fc2 = fc.map(
                lambda feature: feature.set(
                    new_property_name, ee.List(feature.get(property_name)).distinct()
                )
            )
            return fc2.map(
                lambda feature: ee.Feature(feature.geometry()).copyProperties(
                    source=feature, exclude=[property_name]
                )
            )

        # Create grid over AOI
        aoi_grid = aoi.geometry().coveringGrid("EPSG:4326", grid_size)
        aoi_grid_size = aoi_grid.size().getInfo()

        # Process grid with adaptive limit
        limit_value = 40
        increment_step = 20

        while True:
            if limit_value > aoi_grid_size:
                limit_value = aoi_grid_size

            filtered_elements = aoi_grid.limit(limit_value).map(process_grid_element)
            results_pre = ee.FeatureCollection(filtered_elements).flatten()

            num_elements = results_pre.size().getInfo()

            if num_elements >= max_alerts or limit_value == aoi_grid_size:
                results = results_pre
                break

            limit_value += increment_step

        # Apply distinct to alert types
        results2 = apply_distinct(results, "alert_type_list", "alert_type_unique")

        # Sort based on method
        sort_map = {
            "largest_first": ("count", False),
            "smallest_first": ("count", True),
            "newest_first": ("alert_date_max", False),
            "oldest_first": ("alert_date_max", True),
        }

        sort_property, ascending = sort_map.get(sorting_method, ("count", False))
        bb_sorted = results2.sort(sort_property, ascending)

        results_list = bb_sorted.toList(max_alerts)

        return self.evaluate_with_retry(results_list)

    def _convert_to_geopandas(self, polygon_features: List[Dict]) -> gpd.GeoDataFrame:
        """
        Convert list of polygon features to GeoDataFrame.

        Args:
            polygon_features: List of feature dictionaries from GEE

        Returns:
            GeoDataFrame with alerts
        """
        # Handle empty results
        if not polygon_features:
            # Return empty GeoDataFrame with expected columns
            empty_gdf = gpd.GeoDataFrame(
                columns=[
                    "gee_id",
                    "count",
                    "alert_date_min",
                    "alert_date_max",
                    "status",
                    "alert_sources",
                    "description",
                    "area_ha",
                    "bounding_box",
                    "alert_type_unique",
                ],
                geometry="bounding_box",
                crs="EPSG:4326",
            )
            return empty_gdf

        combined_features = []

        for feature in polygon_features:
            polygon = Polygon(feature["geometry"]["coordinates"][0])

            properties = feature["properties"]
            properties["gee_id"] = feature["id"]
            properties["bounding_box"] = polygon
            properties["point"] = polygon.centroid

            combined_features.append(properties)

        # Create GeoDataFrame
        gdf = gpd.GeoDataFrame(combined_features, geometry="point")
        gdf.set_crs(epsg=4326, allow_override=True, inplace=True)

        # Add status tracking columns
        gdf["status"] = "Not reviewed"

        # Handle alert sources - check if alert_type_unique exists (multi-source) or not (CCDC)
        if "alert_type_unique" in gdf.columns:
            gdf["alert_sources"] = gdf["alert_type_unique"].apply(
                lambda x: self._format_alert_sources(x)
            )
        else:
            # CCDC format - single source
            gdf["alert_sources"] = "CCDC"
            gdf["alert_type_unique"] = [
                [1000] for _ in range(len(gdf))
            ]  # Add dummy for compatibility

        gdf["description"] = ""

        # Calculate area from bounding_box column
        gdf_temp = gdf.set_geometry("bounding_box")
        gdf_temp.set_crs(epsg=4326, allow_override=True, inplace=True)
        gdf["area_ha"] = (gdf_temp.to_crs(epsg=3857).geometry.area / 10000).round(2)

        # Drop unnecessary columns if present
        if "label" in gdf.columns:
            gdf.drop("label", axis=1, inplace=True)

        return gdf

    def _format_alert_sources(self, alert_list) -> str:
        """Format list of alert sources into readable string."""
        if not alert_list:
            return ""

        unique_alerts = set()
        for value in alert_list:
            try:
                value = int(value)
            except (ValueError, TypeError):
                continue

            # Check GLAD-L (ones digit)
            if value % 10 in [1, 2]:
                unique_alerts.add("GLAD-L")

            # Check RADD (tens digit)
            if (value % 100) // 10 in [1, 2]:
                unique_alerts.add("RADD")

            # Check GLAD-S2 (hundreds digit)
            if (value % 1000) // 100 in [1, 2]:
                unique_alerts.add("GLAD-S2")

            # Check CCDC (thousands digit)
            if value // 1000 in [1, 2]:
                unique_alerts.add("CCDC")

        alert_names = list(unique_alerts)
        if len(alert_names) == 1:
            return alert_names[0]
        elif len(alert_names) == 2:
            return f"{alert_names[0]} and {alert_names[1]}"
        else:
            return f"{', '.join(alert_names[:-1])} and {alert_names[-1]}"

    # Navigation methods
    def get_current_alert(self) -> Optional[pd.Series]:
        """Get the current alert being viewed."""
        if self.alerts_gdf is None or self.alerts_gdf.empty:
            return None
        return self.alerts_gdf.iloc[self.current_index]

    def next_alert(self) -> Optional[pd.Series]:
        """Navigate to the next alert."""
        if self.alerts_gdf is None or self.alerts_gdf.empty:
            return None

        if self.current_index < len(self.alerts_gdf) - 1:
            self.current_index += 1

        return self.get_current_alert()

    def previous_alert(self) -> Optional[pd.Series]:
        """Navigate to the previous alert."""
        if self.alerts_gdf is None or self.alerts_gdf.empty:
            return None

        if self.current_index > 0:
            self.current_index -= 1

        return self.get_current_alert()

    def go_to_alert(self, index: int) -> Optional[pd.Series]:
        """Navigate to a specific alert by index."""
        if self.alerts_gdf is None or self.alerts_gdf.empty:
            return None

        if 0 <= index < len(self.alerts_gdf):
            self.current_index = index
            return self.get_current_alert()

        return None

    def get_alert_count(self) -> int:
        """Get total number of alerts."""
        if self.alerts_gdf is None:
            return 0
        return len(self.alerts_gdf)

    def get_current_index(self) -> int:
        """Get current alert index."""
        return self.current_index

    def filter_by_status(self, status: str) -> gpd.GeoDataFrame:
        """
        Filter alerts by review status.

        Args:
            status: Status to filter by (e.g., "Confirmed", "Not reviewed", etc.)

        Returns:
            Filtered GeoDataFrame
        """
        if self.alerts_gdf is None:
            return gpd.GeoDataFrame()

        return self.alerts_gdf[self.alerts_gdf["status"] == status]

    def update_alert_status(self, index: int, status: str, description: str = ""):
        """
        Update the status and description of an alert.

        Args:
            index: Index of the alert to update
            status: New status value
            description: Optional description text
        """
        if self.alerts_gdf is not None and 0 <= index < len(self.alerts_gdf):
            self.alerts_gdf.at[index, "status"] = status
            if description:
                self.alerts_gdf.at[index, "description"] = description

    def export_to_file(self, filepath: str, format: str = "gpkg"):
        """
        Export alerts GeoDataFrame to file.

        Args:
            filepath: Output file path
            format: Output format ("gpkg", "geojson", "shp", "csv")
        """
        if self.alerts_gdf is None:
            raise ValueError("No alerts to export. Run group_alerts() first.")

        if format == "csv":
            # For CSV, convert geometry to WKT
            df = self.alerts_gdf.copy()
            df["geometry_wkt"] = df["geometry"].apply(lambda x: x.wkt)
            df.drop(
                columns=["geometry", "bounding_box", "point"], errors="ignore"
            ).to_csv(filepath, index=False)
        elif format == "gpkg":
            self.alerts_gdf.to_file(filepath, driver="GPKG")
        elif format == "geojson":
            self.alerts_gdf.to_file(filepath, driver="GeoJSON")
        elif format == "shp":
            self.alerts_gdf.to_file(filepath, driver="ESRI Shapefile")
        else:
            raise ValueError(f"Unsupported format: {format}")

    def get_alert_imagery(
        self,
        alert_index: Optional[int] = None,
        satellite: str = "sentinel2",
        buffer_m: float = 500,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> ee.Image:
        """
        Get satellite imagery for an alert.

        Args:
            alert_index: Index of alert (None for current)
            satellite: Satellite source ("sentinel2", "landsat8", "planet")
            buffer_m: Buffer around alert in meters
            start_date: Start date for imagery (YYYY-MM-DD)
            end_date: End date for imagery (YYYY-MM-DD)

        Returns:
            Earth Engine Image
        """
        if self.alerts_gdf is None or self.alerts_gdf.empty:
            raise ValueError("No alerts available")

        if alert_index is None:
            alert_index = self.current_index

        alert = self.alerts_gdf.iloc[alert_index]
        bbox = alert["bounding_box"]

        # Create buffered geometry
        bbox_ee = ee.Geometry.Polygon([list(bbox.exterior.coords)])
        buffered = bbox_ee.buffer(buffer_m)

        # Get date range
        if start_date is None or end_date is None:
            alert_date = alert["alert_date_max"]
            # Convert Julian date to datetime if needed
            if alert_date > 2000:  # Julian date format
                year = int(alert_date)
                day = int((alert_date - year) * 365)
                from datetime import datetime, timedelta

                date_obj = datetime(year, 1, 1) + timedelta(days=day)
                end_date = date_obj.strftime("%Y-%m-%d")
                start_date = (date_obj - timedelta(days=60)).strftime("%Y-%m-%d")

        # Get imagery based on satellite
        if satellite == "sentinel2":
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(buffered)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
                .select(["B4", "B3", "B2"])
            )
        elif satellite == "landsat8":
            collection = (
                ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
                .filterBounds(buffered)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt("CLOUD_COVER", 20))
                .select(["SR_B4", "SR_B3", "SR_B2"])
            )
        elif satellite == "planet":
            collection = (
                ee.ImageCollection("projects/planet-nicfi/assets/basemaps/americas")
                .filterBounds(buffered)
                .filterDate(start_date, end_date)
                .select(["R", "G", "B"])
            )
        else:
            raise ValueError(f"Unknown satellite: {satellite}")

        # Get median composite
        image = collection.median().clip(buffered)

        return image

    def display_alert(
        self,
        alert_index: Optional[int] = None,
        satellite: str = "sentinel2",
        buffer_m: float = 500,
        figsize: Tuple[int, int] = (12, 10),
        show_bbox: bool = True,
    ):
        """
        Display satellite imagery for an alert using matplotlib.

        Args:
            alert_index: Index of alert (None for current)
            satellite: Satellite source ("sentinel2", "landsat8", "planet")
            buffer_m: Buffer around alert in meters
            figsize: Figure size (width, height)
            show_bbox: Whether to overlay the alert bounding box
        """
        if self.alerts_gdf is None or self.alerts_gdf.empty:
            raise ValueError("No alerts available")

        if alert_index is None:
            alert_index = self.current_index

        alert = self.alerts_gdf.iloc[alert_index]
        bbox = alert["bounding_box"]

        # Get imagery
        image = self.get_alert_imagery(alert_index, satellite, buffer_m)

        # Get geometry bounds
        bbox_ee = ee.Geometry.Polygon([list(bbox.exterior.coords)])
        buffered = bbox_ee.buffer(buffer_m)
        bounds = buffered.bounds().getInfo()["coordinates"][0]

        # Extract bounds
        min_lon = min([p[0] for p in bounds])
        max_lon = max([p[0] for p in bounds])
        min_lat = min([p[1] for p in bounds])
        max_lat = max([p[1] for p in bounds])

        # Define visualization parameters
        if satellite == "sentinel2":
            vis_params = {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"]}
        elif satellite == "landsat8":
            vis_params = {
                "min": 7000,
                "max": 12000,
                "bands": ["SR_B4", "SR_B3", "SR_B2"],
            }
        elif satellite == "planet":
            vis_params = {"min": 0, "max": 255, "bands": ["R", "G", "B"]}

        # Get thumbnail URL
        region = buffered.getInfo()
        url = image.getThumbURL(
            {**vis_params, "region": region, "dimensions": 1024, "format": "png"}
        )

        # Download and display
        response = requests.get(url)
        img = Image.open(BytesIO(response.content))

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Display image
        ax.imshow(img, extent=[min_lon, max_lon, min_lat, max_lat])

        # Overlay bounding box
        if show_bbox:
            bbox_coords = list(bbox.exterior.coords)
            bbox_lons = [p[0] for p in bbox_coords]
            bbox_lats = [p[1] for p in bbox_coords]
            ax.plot(bbox_lons, bbox_lats, "r-", linewidth=2, label="Alert Area")

        # Add info
        title = f"Alert {alert_index + 1}/{len(self.alerts_gdf)}\n"
        title += f"Source: {alert['alert_sources']} | "
        title += f"Area: {alert['area_ha']} ha | "
        title += f"Status: {alert['status']}"

        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")

        if show_bbox:
            ax.legend()

        plt.tight_layout()
        plt.show()

        return fig, ax


# Example usage
if __name__ == "__main__":
    # Initialize Earth Engine
    ee.Initialize()

    # Example: Load alerts from a GEE asset
    asset_id = "your/gee/asset/path"

    # Create navigator
    navigator = AlertGroupingNavigator(asset_id=asset_id, pixel_size=30)

    # Define area of interest (example using coordinates)
    aoi = ee.Geometry.Rectangle([-74.2, -10.0, -74.0, -9.8])
    aoi_fc = ee.FeatureCollection([ee.Feature(aoi)])

    # Group alerts
    alerts_gdf = navigator.group_alerts(
        aoi=aoi_fc,
        min_alert_size_pixels=5,
        max_alerts=50,
        sorting_method="largest_first",
        grid_size=150000,
    )

    print(f"Found {navigator.get_alert_count()} alerts")

    # Navigate through alerts
    current = navigator.get_current_alert()
    print(f"Current alert: {current['alert_sources']}, Area: {current['area_ha']} ha")

    # Move to next alert
    next_alert = navigator.next_alert()
    print(
        f"Next alert: {next_alert['alert_sources']}, Area: {next_alert['area_ha']} ha"
    )

    # Update status
    navigator.update_alert_status(0, "Confirmed", "Deforestation confirmed")

    # Export results
    navigator.export_to_file("alerts_output.gpkg", format="gpkg")
