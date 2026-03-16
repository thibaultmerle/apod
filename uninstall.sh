#!/bin/bash
# Uninstall script for APOD Wallpaper Overlay

echo "=========================================="
echo "APOD Wallpaper Overlay - Uninstall"
echo "=========================================="
echo ""

# Stop and disable services
echo "1. Stopping and disabling services..."

if systemctl --user is-active apod-wallpaper-overlay.timer &> /dev/null; then
    systemctl --user stop apod-wallpaper-overlay.timer
    echo "✓ Stopped overlay timer"
fi

if systemctl --user is-enabled apod-wallpaper-overlay.timer &> /dev/null; then
    systemctl --user disable apod-wallpaper-overlay.timer
    echo "✓ Disabled overlay timer"
fi

# Remove systemd files
echo ""
echo "2. Removing systemd service files..."

if [ -f ~/.config/systemd/user/apod-wallpaper-overlay.service ]; then
    rm ~/.config/systemd/user/apod-wallpaper-overlay.service
    echo "✓ Removed overlay service"
fi

if [ -f ~/.config/systemd/user/apod-wallpaper-overlay.timer ]; then
    rm ~/.config/systemd/user/apod-wallpaper-overlay.timer
    echo "✓ Removed overlay timer"
fi

systemctl --user daemon-reload

# Ask about output directory
echo ""
read -p "Remove output directory ~/dev/apod/pic? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf ~/dev/apod/pic
    echo "✓ Removed output directory"
else
    echo "⊘ Kept output directory"
fi

# Restore original wallpaper
echo ""
read -p "Restore original wallpaper (from Random Wallpaper extension)? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Get the latest wallpaper from the cache
    latest_wallpaper=$(ls -t ~/.cache/randomwallpaper@iflow.space/wallpapers/*.jpg ~/.cache/randomwallpaper@iflow.space/wallpapers/*.png 2>/dev/null | grep -v "apod/pic" | head -n 1)
    if [ -n "$latest_wallpaper" ]; then
        gsettings set org.gnome.desktop.background picture-uri "file://$latest_wallpaper"
        gsettings set org.gnome.desktop.background picture-uri-dark "file://$latest_wallpaper"
        echo "✓ Restored wallpaper"
    else
        echo "⚠️  Could not find original wallpaper"
    fi
else
    echo "⊘ Kept current wallpaper"
fi

echo ""
echo "=========================================="
echo "Uninstall Complete"
echo "=========================================="
echo ""
echo "The scripts in ~/dev/apod are still present."
echo "You can delete them manually if desired."
echo ""
