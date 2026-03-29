#!/bin/sh
set -e

# Add secondary IP addresses for virtual cameras
# The primary IP is assigned by Docker's macvlan network.
# Additional IPs (from SECONDARY_IPS env var) are added here.
# Format: SECONDARY_IPS="192.168.2.162/24,192.168.2.163/24,..."

if [ -n "$SECONDARY_IPS" ]; then
    echo "Adding secondary IPs..."
    IFS=','
    for ip in $SECONDARY_IPS; do
        echo "  Adding $ip to eth0"
        ip addr add "$ip" dev eth0 || true
    done
    unset IFS
fi

echo "Starting ONVIF Splitter..."
exec python -m onvif_splitter "$@"
