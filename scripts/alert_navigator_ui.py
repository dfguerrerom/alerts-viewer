"""
Alert Navigator UI Module
Interactive visualization interface for navigating deforestation alerts
"""

import ee
import ipywidgets as widgets
from IPython.display import display, clear_output
import matplotlib.pyplot as plt
import requests
from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta
import numpy as np


class AlertNavigatorUI:
    """Interactive UI for navigating and visualizing deforestation alerts."""

    def __init__(self, navigator):
        """
        Initialize the UI with an AlertGroupingNavigator instance.

        Args:
            navigator: AlertGroupingNavigator instance with loaded alerts
        """
        self.navigator = navigator
        self._setup_widgets()
        self._attach_handlers()

    @staticmethod
    def _decimal_year_to_date(decimal_year):
        """
        Convert decimal year to readable date string.
        Example: 2024.026 -> 2024-01-10

        Args:
            decimal_year: Float representing year as decimal

        Returns:
            str: Date in YYYY-MM-DD format, or "N/A" if invalid
        """
        # Handle invalid or missing dates
        if decimal_year is None or decimal_year <= 0 or decimal_year < 1900:
            return "N/A"

        year = int(decimal_year)
        fraction = decimal_year - year

        try:
            start_of_year = datetime(year, 1, 1)
            # Calculate days in year (accounting for leap years)
            if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                days_in_year = 366
            else:
                days_in_year = 365

            days_offset = fraction * days_in_year
            date = start_of_year + timedelta(days=days_offset)

            return date.strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            return "N/A"

    def _setup_widgets(self):
        """Create all UI widgets."""
        # Output areas
        self.output_info = widgets.Output()
        self.output_images = widgets.Output()

        # Navigation buttons (no colors)
        self.btn_first = widgets.Button(
            description="⏮ First", layout=widgets.Layout(width="100px")
        )
        self.btn_prev = widgets.Button(
            description="◀ Previous", layout=widgets.Layout(width="100px")
        )
        self.btn_next = widgets.Button(
            description="Next ▶", layout=widgets.Layout(width="100px")
        )
        self.btn_last = widgets.Button(
            description="Last ⏭", layout=widgets.Layout(width="100px")
        )

        # Satellite source dropdown
        self.satellite_dropdown = widgets.Dropdown(
            options=["sentinel2", "planet", "landsat8"],
            value="sentinel2",
            description="Satellite:",
            style={"description_width": "80px"},
        )

        # Buffer slider
        self.buffer_slider = widgets.IntSlider(
            value=500,
            min=100,
            max=2000,
            step=100,
            description="Buffer (m):",
            style={"description_width": "80px"},
            layout=widgets.Layout(width="400px"),
        )

        # Refresh button (no color)
        self.btn_refresh = widgets.Button(
            description="🔄 Refresh Images", layout=widgets.Layout(width="150px")
        )

        # Alert label
        self.alert_label = widgets.HTML(
            value=f"<b>Alert: 1 / {self.navigator.get_alert_count()}</b>"
        )

    def _attach_handlers(self):
        """Attach event handlers to widgets."""
        self.btn_first.on_click(self._on_first_clicked)
        self.btn_prev.on_click(self._on_prev_clicked)
        self.btn_next.on_click(self._on_next_clicked)
        self.btn_last.on_click(self._on_last_clicked)
        self.btn_refresh.on_click(self._on_refresh_clicked)

    def _display_alert_pixels(self, current_alert, ax, buffered_geom=None, extent=None):
        """
        Display the actual alert pixels as the first visualization.

        Args:
            current_alert: Current alert data dictionary
            ax: Matplotlib axis to plot on
            buffered_geom: Optional buffered geometry to use instead of alert bbox
            extent: Optional extent [min_lon, max_lon, min_lat, max_lat] for display
        """
        try:
            # Get alert geometry
            bbox = current_alert["bounding_box"]
            bbox_ee = ee.Geometry.Polygon([list(bbox.exterior.coords)])

            # Use buffered geometry if provided, otherwise use alert bbox
            clip_geom = buffered_geom if buffered_geom is not None else bbox_ee

            # Get the alert image from the asset or use provided image
            if self.navigator.alert_image is not None:
                alert_image = self.navigator.alert_image
            else:
                alert_image = ee.Image(self.navigator.asset_id)

            # Try to select appropriate band for visualization
            band_names = alert_image.bandNames().getInfo()

            # Determine which band to use for visualization
            if "alert" in band_names:
                vis_band = "alert"
            elif "detection_count" in band_names:
                vis_band = "detection_count"
            elif "difference" in band_names:
                vis_band = "difference"
            else:
                # Use first band as fallback
                vis_band = band_names[0] if band_names else "alert"

            # Clip to geometry and create binary mask (alert > 0)
            alert_clipped = alert_image.select(vis_band).clip(clip_geom)
            alert_binary = alert_clipped.gt(
                0
            ).selfMask()  # Create binary mask of alert pixels

            # Get thumbnail - only show pixels where alert exists
            region = clip_geom.getInfo()
            url = alert_binary.getThumbURL(
                {
                    "min": 0,
                    "max": 1,
                    "palette": ["FF0000"],  # Red for alert pixels
                    "region": region,
                    "dimensions": 512,
                    "format": "png",
                }
            )

            # Download and display
            response = requests.get(url)
            img = Image.open(BytesIO(response.content))

            # Use provided extent or calculate from geometry
            if extent is not None:
                min_lon, max_lon, min_lat, max_lat = extent
            else:
                bounds = clip_geom.bounds().getInfo()["coordinates"][0]
                min_lon = min([p[0] for p in bounds])
                max_lon = max([p[0] for p in bounds])
                min_lat = min([p[1] for p in bounds])
                max_lat = max([p[1] for p in bounds])

            # Display
            ax.imshow(img, extent=[min_lon, max_lon, min_lat, max_lat])
            ax.set_title("Alert Pixels", fontsize=12, fontweight="bold")
            ax.set_xlabel("Longitude", fontsize=10)
            ax.set_ylabel("Latitude", fontsize=10)

            # Reduce number of ticks
            ax.locator_params(axis="x", nbins=4)
            ax.locator_params(axis="y", nbins=4)

        except Exception as e:
            ax.text(
                0.5,
                0.5,
                f"Error loading alert pixels:\n{str(e)}",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )

    def _display_satellite_images(self):
        """Display satellite imagery for current alert."""
        with self.output_images:
            clear_output(wait=True)

            try:
                current = self.navigator.get_current_alert()
                idx = self.navigator.get_current_index()
                satellite = self.satellite_dropdown.value
                buffer_m = self.buffer_slider.value

                print(f"Loading {satellite.upper()} imagery (buffer: {buffer_m}m)...")

                # Get alert bbox
                bbox = current["bounding_box"]
                bbox_ee = ee.Geometry.Polygon([list(bbox.exterior.coords)])
                buffered = bbox_ee.buffer(buffer_m)

                # Get alert dates
                alert_date_max = current["alert_date_max"]

                # Convert Julian date to datetime
                if alert_date_max > 2000:  # Julian date format
                    year = int(alert_date_max)
                    day = int((alert_date_max - year) * 365)
                    alert_date_obj = datetime(year, 1, 1) + timedelta(days=day)

                    # Define before/after periods
                    before_end = alert_date_obj - timedelta(days=15)
                    before_start = before_end - timedelta(days=90)
                    after_start = alert_date_obj + timedelta(days=15)
                    after_end = after_start + timedelta(days=90)

                    before_start_str = before_start.strftime("%Y-%m-%d")
                    before_end_str = before_end.strftime("%Y-%m-%d")
                    after_start_str = after_start.strftime("%Y-%m-%d")
                    after_end_str = after_end.strftime("%Y-%m-%d")
                else:
                    print("Invalid date format")
                    return

                # Get imagery based on satellite
                if satellite == "sentinel2":
                    collection_before = (
                        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                        .filterBounds(buffered)
                        .filterDate(before_start_str, before_end_str)
                        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
                        .select(["B4", "B3", "B2"])
                    )
                    image_before = collection_before.median().clip(buffered)

                    collection_after = (
                        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                        .filterBounds(buffered)
                        .filterDate(after_start_str, after_end_str)
                        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
                        .select(["B4", "B3", "B2"])
                    )
                    image_after = collection_after.median().clip(buffered)

                    vis_params = {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"]}

                elif satellite == "landsat8":
                    collection_before = (
                        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
                        .filterBounds(buffered)
                        .filterDate(before_start_str, before_end_str)
                        .filter(ee.Filter.lt("CLOUD_COVER", 30))
                        .select(["SR_B4", "SR_B3", "SR_B2"])
                    )
                    image_before = collection_before.median().clip(buffered)

                    collection_after = (
                        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
                        .filterBounds(buffered)
                        .filterDate(after_start_str, after_end_str)
                        .filter(ee.Filter.lt("CLOUD_COVER", 30))
                        .select(["SR_B4", "SR_B3", "SR_B2"])
                    )
                    image_after = collection_after.median().clip(buffered)

                    vis_params = {
                        "min": 7000,
                        "max": 12000,
                        "bands": ["SR_B4", "SR_B3", "SR_B2"],
                    }

                elif satellite == "planet":
                    collection_before = (
                        ee.ImageCollection(
                            "projects/planet-nicfi/assets/basemaps/americas"
                        )
                        .filterBounds(buffered)
                        .filterDate(before_start_str, before_end_str)
                        .select(["R", "G", "B"])
                    )
                    image_before = collection_before.mosaic().clip(buffered)

                    collection_after = (
                        ee.ImageCollection(
                            "projects/planet-nicfi/assets/basemaps/americas"
                        )
                        .filterBounds(buffered)
                        .filterDate(after_start_str, after_end_str)
                        .select(["R", "G", "B"])
                    )
                    image_after = collection_after.mosaic().clip(buffered)

                    vis_params = {"min": 0, "max": 255, "bands": ["R", "G", "B"]}

                # Get geometry bounds
                bounds = buffered.bounds().getInfo()["coordinates"][0]
                min_lon = min([p[0] for p in bounds])
                max_lon = max([p[0] for p in bounds])
                min_lat = min([p[1] for p in bounds])
                max_lat = max([p[1] for p in bounds])

                # Get thumbnails
                region = buffered.getInfo()

                url_before = image_before.getThumbURL(
                    {**vis_params, "region": region, "dimensions": 512, "format": "png"}
                )

                url_after = image_after.getThumbURL(
                    {**vis_params, "region": region, "dimensions": 512, "format": "png"}
                )

                # Download images
                response_before = requests.get(url_before)
                img_before = Image.open(BytesIO(response_before.content))

                response_after = requests.get(url_after)
                img_after = Image.open(BytesIO(response_after.content))

                # Create figure with alert pixels + before/after comparison
                fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(20, 6))

                # Alert pixels (first image) - use buffered extent
                self._display_alert_pixels(
                    current,
                    ax1,
                    buffered_geom=buffered,
                    extent=[min_lon, max_lon, min_lat, max_lat],
                )

                # Before image
                ax2.imshow(img_before, extent=[min_lon, max_lon, min_lat, max_lat])
                bbox_coords = list(bbox.exterior.coords)
                bbox_lons = [p[0] for p in bbox_coords]
                bbox_lats = [p[1] for p in bbox_coords]
                ax2.plot(bbox_lons, bbox_lats, "r-", linewidth=2, label="Alert Area")
                ax2.set_title(
                    f"BEFORE\n{before_start_str} to {before_end_str}",
                    fontsize=12,
                    fontweight="bold",
                )
                ax2.set_xlabel("Longitude", fontsize=10)
                ax2.set_ylabel("Latitude", fontsize=10)
                ax2.legend()
                ax2.locator_params(axis="x", nbins=4)
                ax2.locator_params(axis="y", nbins=4)

                # After image
                ax3.imshow(img_after, extent=[min_lon, max_lon, min_lat, max_lat])
                ax3.plot(bbox_lons, bbox_lats, "r-", linewidth=2, label="Alert Area")
                ax3.set_title(
                    f"AFTER\n{after_start_str} to {after_end_str}",
                    fontsize=12,
                    fontweight="bold",
                )
                ax3.set_xlabel("Longitude", fontsize=10)
                ax3.set_ylabel("Latitude", fontsize=10)
                ax3.legend()
                ax3.locator_params(axis="x", nbins=4)
                ax3.locator_params(axis="y", nbins=4)

                # Main title
                fig.suptitle(
                    f"Alert {idx + 1}/{self.navigator.get_alert_count()} | {satellite.upper()} | "
                    f'{current["alert_sources"]} | {current["area_ha"]:.2f} ha | '
                    f'{current["count"]} pixels',
                    fontsize=14,
                    fontweight="bold",
                )

                plt.tight_layout()
                plt.show()

            except Exception as e:
                print(f"Error loading imagery: {e}")
                import traceback

                traceback.print_exc()

    def _display_alert_info(self):
        """Display information about current alert."""
        with self.output_info:
            clear_output(wait=True)

            current = self.navigator.get_current_alert()
            idx = self.navigator.get_current_index()
            total = self.navigator.get_alert_count()

            # Update label
            self.alert_label.value = f"<b>Alert: {idx + 1} / {total}</b>"

            # Calculate actual area (verify calculation)
            pixel_count = current["count"]
            pixel_size_m = self.navigator.pixel_size
            area_m2 = pixel_count * (pixel_size_m**2)
            area_ha = area_m2 / 10000

            # Convert decimal dates to readable format
            date_min_str = self._decimal_year_to_date(current["alert_date_min"])
            date_max_str = self._decimal_year_to_date(current["alert_date_max"])

            # Display alert info
            print("=" * 70)
            print(f"ALERT {idx + 1} of {total}")
            print("=" * 70)
            print(f"Alert Sources: {current['alert_sources']}")
            print(f"Pixel Count: {pixel_count} pixels")
            print(f"Pixel Size: {pixel_size_m} m")
            print(f"Calculated Area: {area_ha:.2f} ha ({area_m2:.2f} m²)")
            print(f"Stored Area: {current['area_ha']:.2f} ha")
            print(f"Date Range: {date_min_str} to {date_max_str}")
            print(f"Location: ({current['point'].y:.4f}, {current['point'].x:.4f})")
            print("=" * 70)

    def _update_display(self):
        """Update both info and images."""
        self._display_alert_info()
        self._display_satellite_images()

    def _on_first_clicked(self, b):
        self.navigator.go_to_alert(0)
        self._update_display()

    def _on_prev_clicked(self, b):
        self.navigator.previous_alert()
        self._update_display()

    def _on_next_clicked(self, b):
        self.navigator.next_alert()
        self._update_display()

    def _on_last_clicked(self, b):
        self.navigator.go_to_alert(self.navigator.get_alert_count() - 1)
        self._update_display()

    def _on_refresh_clicked(self, b):
        """Refresh images with current satellite/buffer settings."""
        self._display_satellite_images()

    def display(self):
        """Display the complete UI."""
        # Create layout
        nav_buttons = widgets.HBox(
            [
                self.btn_first,
                self.btn_prev,
                self.btn_next,
                self.btn_last,
                self.alert_label,
            ]
        )

        imagery_controls = widgets.HBox(
            [
                self.satellite_dropdown,
                self.buffer_slider,
                self.btn_refresh,
            ]
        )

        # Display the widget
        display(widgets.HTML("<h3>🛰️ Navigation & Imagery Controls</h3>"))
        display(nav_buttons)
        display(imagery_controls)
        display(widgets.HTML("<h3>📝 Alert Information</h3>"))
        display(self.output_info)
        display(widgets.HTML("<h3>🖼️ Satellite Imagery Visualization</h3>"))
        display(self.output_images)

        # Show first alert
        self._update_display()

        print("\n✓ Interactive navigator ready!")
