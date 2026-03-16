#!/bin/bash
# Setup script for APOD Wallpaper Overlay

set -e

echo "=========================================="
echo "APOD Wallpaper Overlay - Setup"
echo "=========================================="
echo ""

# Check if running on GNOME
if ! command -v gnome-shell &> /dev/null; then
    echo "⚠️  Warning: GNOME Shell not found. This tool is designed for GNOME."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check System dependencies (ImageMagick)
echo "1. Checking System dependencies..."
if command -v convert &> /dev/null; then
    echo "✓ ImageMagick (convert) is already installed"
else
    echo "⚠️  Missing ImageMagick. Installing..."
    if command -v apt &> /dev/null; then
        sudo apt-get install -y imagemagick
    else
        echo "⚠️  Please install ImageMagick manually (required for high-quality text rendering)."
    fi
fi

# Check Python dependencies
echo ""
echo "2. Checking Python dependencies..."
if python3 -c "import requests, PIL" 2>/dev/null; then
    echo "✓ All required packages (requests, pillow) are already installed"
else
    echo "⚠️  Missing dependencies. Installing..."
    
    # Try system packages first
    if command -v apt &> /dev/null; then
        echo "   Attempting to install via apt..."
        sudo apt-get install -y python3-requests python3-pil 2>/dev/null || true
    fi
    
    # Check again
    if python3 -c "import requests, PIL" 2>/dev/null; then
        echo "✓ Dependencies installed via system packages"
    else
        # Try pip with --break-system-packages if needed (newer Debian/Ubuntu)
        if command -v pip3 &> /dev/null; then
            echo "   Attempting pip install..."
            pip3 install --user requests pillow 2>/dev/null || \
            pip3 install --user --break-system-packages requests pillow 2>/dev/null || \
            echo "⚠️  Could not install via pip. Please install manually:"
            echo "   sudo apt-get install python3-requests python3-pil"
        fi
    fi
fi

# Make scripts executable
echo ""
echo "3. Making scripts executable..."
chmod +x "$(dirname "$0")/apod_wallpaper_overlay.py"
echo "✓ Scripts are executable"

# Test the overlay
echo ""
echo "4. Testing overlay application..."
python3 "$(dirname "$0")/apod_wallpaper_overlay.py"

if [ $? -eq 0 ]; then
    echo "✓ Overlay test successful!"
else
    echo "✗ Overlay test failed. Please check the errors above."
    exit 1
fi

# Setup systemd services
echo ""
echo "5. Setting up systemd services..."
mkdir -p ~/.config/systemd/user

# Install timer service (Default)
echo "Installing update timer..."
cp "$(dirname "$0")/apod-wallpaper-overlay.service" ~/.config/systemd/user/
cp "$(dirname "$0")/apod-wallpaper-overlay.timer" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable apod-wallpaper-overlay.timer
systemctl --user start apod-wallpaper-overlay.timer
echo "✓ Timer installed and started (updates every 4 hours)"

# Summary
echo ""
echo "=========================================="
echo "Setup Complete! 🎉"
echo "=========================================="
echo ""
echo "Your wallpaper should now have APOD information overlay!"
echo ""
echo "Useful commands:"
echo "  • Apply overlay now:"
echo "    python3 ~/dev/apod/apod_wallpaper_overlay.py"
echo ""
echo "  • Check timer status:"
echo "    systemctl --user list-timers --all | grep apod"
echo ""
echo "  • View logs:"
echo "    journalctl --user -u apod-wallpaper-overlay.service -f"
echo ""
echo "Read README.md for more information and customization options."
echo ""
