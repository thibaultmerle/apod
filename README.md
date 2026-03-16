# APOD Wallpaper Overlay

A standalone automated tool designed for **Linux** systems using the **GNOME Desktop Environment**. It automatically downloads the [NASA Astronomy Picture of the Day (APOD)](https://apod.nasa.gov/), generates high-quality information overlays, and updates the desktop background.

## Overview

The application performs the following automated tasks:
1. Retrieves metadata and high-resolution imagery from the NASA APOD API.
2. Generates an aesthetic information overlay including the title, date, explanation, and copyright information.
3. Automatically detects screen resolution and Desktop Environment scaling parameters (e.g., 'zoom', 'scaled') to ensure precise text positioning.
4. Manages local storage by performing periodic cleanup of the image repository to maintain a specified disk quota.

## Installation

To initialize the application and its dependencies, first clone the repository and navigate into the project directory:

```bash
git clone https://github.com/thibaultmerle/apod.git
cd apod
```

Then, execute the provided setup script:

```bash
chmod +x setup.sh
./setup.sh
```

This script will verify python dependencies, configure executable permissions, and register a systemd user timer to automate updates every 4 hours.

## Requirements

*   System: Linux with GNOME Desktop Environment
*   Runtime: Python 3.6 or higher
*   Dependencies: `Pillow`, `requests` (automated by setup script)
*   Rendering Engine: `ImageMagick` (required for Pango-based typography)

## Manual Execution and Testing

The script supports manual execution for immediate updates or for retrieving specific historical dates.

```bash
# Update to the current day's APOD
python3 ./apod_wallpaper_overlay.py

# Retrieve a specific date (Format: YYYYMMDD)
python3 ./apod_wallpaper_overlay.py 20240101
```

## System Integration

The application integrates with `systemd` to provide persistent background updates.

```bash
# Verify scheduled update times
systemctl --user list-timers --all | grep apod

# Monitor application logs
journalctl --user -u apod-wallpaper-overlay.service -f
```

## Configuration

Customization of the rendered overlay can be achieved by modifying the configuration constants within `apod_wallpaper_overlay.py`.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `SCREEN_TITLE_SIZE` | Font size for the primary title in screen pixels | 20 |
| `SCREEN_DATE_SIZE` | Font size for metadata and copyright in screen pixels | 12 |
| `SCREEN_EXPLANATION_SIZE` | Font size for the description text in screen pixels | 12 |
| `RESOLUTION_SCALE` | Super-sampling factor for enhanced text sharpness | 8 |
| `PANEL_OPACITY` | Opacity level of the descriptive background panel | 0.92 |
| `MAX_STORAGE_MB` | Maximum disk quota for the image repository in MB | 256 |
| `UPDATE_FREQUENCY_HOURS` | Targeted frequency for background updates | 4 |

### API Authentication
The application includes a standard demonstration key. For production use or to avoid rate limiting, users are encouraged to register for a personal API key at [api.nasa.gov](https://api.nasa.gov/) and update the `NASA_API_KEY` constant.

## Directory Structure

*   `apod_wallpaper_overlay.py`: Primary execution logic and image processing.
*   `open_apod.py`: Helper utility to launch the NASA documentation for the current image.
*   `pic/`: Local repository for source images and generated composites.
*   `setup.sh`: Automated installation and configuration utility.
*   `apod-wallpaper-overlay.*`: Systemd timer and service конфигурации.

## Technical Implementation

The application's execution pipeline is designed for reliability and visual precision:

1.  **Automation Cycle**: Background execution is managed via `systemd` user timers, checking for updates periodically (defined by `UPDATE_FREQUENCY_HOURS`) to ensure the desktop background syncs with the latest NASA release.
2.  **Data Acquisition**: The script performs automated requests to the NASA APOD API to retrieve high-definition image assets and corresponding narrative metadata.
3.  **Adaptive Geometric Scaling**: 
    * The system queries GNOME configuration to detect active desktop scaling modes (e.g., `zoom`, `scaled`, `spanned`).
    * It calculates exact screen-relative pixel margins based on real-time monitor resolution, ensuring consistent text positioning regardless of the source image's native aspect ratio or dimensions.
4.  **Rendering Pipeline**: Overlays are generated using the ImageMagick Pango engine to leverage professional typography standards. Rendering is performed at an internal high resolution (governed by `RESOLUTION_SCALE`) to achieve superior anti-aliasing through super-sampling.
5.  **Composition**: The final composite is produced using Lanczos downsampling, preserving sharp edge definition and text clarity on the destination display.
6.  **Storage Maintenance**: An automated routine enforces the disk quota specified in `MAX_STORAGE_MB` within the `pic/` directory, identifying and purging the least recently modified assets to optimize storage utilization.
