#!/bin/bash
# Download and extract required shared libraries for Chromium headless on Debian bookworm arm64
set -e

LIBS_DIR="$HOME/.local/lib"
DEB_DIR="/tmp/debs"
mkdir -p "$LIBS_DIR" "$DEB_DIR"

ARCH="arm64"
MIRROR="http://deb.debian.org/debian"
POOL="pool/main"

# Map of package -> deb URL path components  
# We need: libnss3, libnspr4, libnssutil3, libdbus-1-3, libatk1.0-0, libatspi2.0-0
#          libxcomposite1, libxdamage1, libxfixes3, libxrandr2, libgbm1, libxkbcommon0, libasound2

declare -A PACKAGES=(
  ["libnss3"]="n/nss/libnss3_3.87.1-1_${ARCH}.deb"
  ["libnspr4"]="n/nspr/libnspr4_4.35-1_${ARCH}.deb"
  ["libdbus-1-3"]="d/dbus/libdbus-1-3_1.14.10-1~deb12u1_${ARCH}.deb"
  ["libatk1.0-0"]="a/atk1.0/libatk1.0-0_2.38.0-4_${ARCH}.deb"
  ["libatspi2.0-0"]="a/at-spi2-core/libatspi2.0-0_2.46.0-5_${ARCH}.deb"
  ["libxcomposite1"]="libx/libxcomposite/libxcomposite1_0.4.5-1_${ARCH}.deb"
  ["libxdamage1"]="libx/libxdamage/libxdamage1_1.1.6-1_${ARCH}.deb"
  ["libxfixes3"]="libx/libxfixes/libxfixes3_6.0.0-2_${ARCH}.deb"
  ["libxrandr2"]="libx/libxrandr/libxrandr2_1.5.2-2+b1_${ARCH}.deb"
  ["libgbm1"]="m/mesa/libgbm1_22.3.6-1+deb12u1_${ARCH}.deb"
  ["libxkbcommon0"]="libx/libxkbcommon/libxkbcommon0_1.5.0-1_${ARCH}.deb"
  ["libasound2"]="a/alsa-lib/libasound2_1.2.8-1+b1_${ARCH}.deb"
)

for pkg in "${!PACKAGES[@]}"; do
  deb_path="${PACKAGES[$pkg]}"
  deb_file="$DEB_DIR/${pkg}.deb"
  url="$MIRROR/$POOL/$deb_path"
  
  if [ ! -f "$deb_file" ]; then
    echo "Downloading $pkg..."
    curl -sL "$url" -o "$deb_file" || { echo "WARN: Failed to download $pkg from $url"; continue; }
  fi
  
  echo "Extracting $pkg..."
  cd "$DEB_DIR"
  ar x "$deb_file" 2>/dev/null || { echo "WARN: Failed to extract $pkg"; continue; }
  
  # Extract data archive
  if [ -f data.tar.xz ]; then
    tar xf data.tar.xz -C / --strip-components=0 2>/dev/null || \
    tar xf data.tar.xz -C "$LIBS_DIR" --strip-components=3 --wildcards "*/lib/*/*.so*" 2>/dev/null || true
    rm -f data.tar.xz
  elif [ -f data.tar.zst ]; then
    tar xf data.tar.zst -C "$LIBS_DIR" --strip-components=3 --wildcards "*/lib/*/*.so*" 2>/dev/null || true
    rm -f data.tar.zst
  elif [ -f data.tar.gz ]; then
    tar xf data.tar.gz -C "$LIBS_DIR" --strip-components=3 --wildcards "*/lib/*/*.so*" 2>/dev/null || true
    rm -f data.tar.gz
  fi
  rm -f control.tar.* debian-binary
done

echo ""
echo "Libraries extracted to $LIBS_DIR:"
ls -la "$LIBS_DIR"/*.so* 2>/dev/null | head -30
echo ""
echo "Add to LD_LIBRARY_PATH: export LD_LIBRARY_PATH=$LIBS_DIR:\$LD_LIBRARY_PATH"
