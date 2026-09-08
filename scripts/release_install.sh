#!/bin/sh
# Install a pre-built plug-in release into the current user's GIMP 3 plug-in
# directory. Bundled into the release archive next to the gimp-comfyui folder
# so it works on Linux/macOS without a Python interpreter.
set -e

script_dir=$(cd "$(dirname "$0")" && pwd)
source_dir="$script_dir/gimp-comfyui"

if [ ! -d "$source_dir" ]; then
    echo "gimp-comfyui folder not found next to this script" >&2
    exit 1
fi

version="${GIMP_VERSION:-3.2}"

if [ -n "$GIMP_PLUGIN_DIR" ]; then
    plugin_root="$GIMP_PLUGIN_DIR"
elif [ -n "$GIMP_CONFIG_DIR" ]; then
    plugin_root="$GIMP_CONFIG_DIR/plug-ins"
elif [ "$(uname)" = "Darwin" ]; then
    plugin_root="$HOME/Library/Application Support/GIMP/$version/plug-ins"
else
    config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
    plugin_root="$config_home/GIMP/$version/plug-ins"
fi

destination="$plugin_root/gimp-comfyui"

rm -rf "$destination"
mkdir -p "$plugin_root"
cp -R "$source_dir" "$destination"
chmod 755 "$destination/gimp-comfyui.py"

echo "Installed to $destination"
