#!/bin/bash
set -e

# ONVIF Splitter installer for UniFi OS
# Run as root on UDM Pro / UDM SE / Cloud Gateway

INSTALL_DIR="/data/onvif-splitter"
SERVICE_NAME="onvif-splitter"

echo "=== ONVIF Splitter Installer for UniFi OS ==="

# Check we're on UniFi OS
if [ ! -f /etc/unifi-os.conf ] && [ ! -d /data ]; then
    echo "Error: This doesn't appear to be a UniFi OS device"
    exit 1
fi

# Install Python3 + pip if missing
if ! command -v python3 &> /dev/null; then
    echo "Installing Python3..."
    apt-get update && apt-get install -y python3 python3-pip python3-venv
fi

# Create install directory
mkdir -p "$INSTALL_DIR"

# Download latest release
echo "Downloading ONVIF Splitter..."
curl -sL "https://github.com/bassrock/onvif-splitter/archive/refs/heads/main.tar.gz" | \
    tar xz --strip-components=1 -C "$INSTALL_DIR"

# Create venv and install deps
echo "Installing dependencies..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# Copy config if not exists
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config.yaml" "$INSTALL_DIR/config.yaml"
    echo ""
    echo "IMPORTANT: Edit $INSTALL_DIR/config.yaml with your NVR settings!"
fi

# Install network setup script
cp "$INSTALL_DIR/unifios/setup-interfaces.sh" "$INSTALL_DIR/setup-interfaces.sh"
chmod +x "$INSTALL_DIR/setup-interfaces.sh"

# Install systemd service
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=ONVIF Splitter - Virtual ONVIF cameras from NVR
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=$INSTALL_DIR/setup-interfaces.sh
ExecStart=$INSTALL_DIR/venv/bin/python -m onvif_splitter $INSTALL_DIR/config.yaml
WorkingDirectory=$INSTALL_DIR
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}

echo ""
echo "=== Installation complete ==="
echo ""
echo "1. Edit config:     nano $INSTALL_DIR/config.yaml"
echo "2. Edit interfaces: nano $INSTALL_DIR/setup-interfaces.sh"
echo "3. Start service:   systemctl start $SERVICE_NAME"
echo "4. Check status:    systemctl status $SERVICE_NAME"
echo "5. View logs:       journalctl -u $SERVICE_NAME -f"
