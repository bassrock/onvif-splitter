#!/bin/bash
set -e

# Add secondary IP addresses for virtual cameras.
# The primary IP is assigned by Docker's macvlan network.
# Format: SECONDARY_IPS="192.168.2.122/24,192.168.2.123/24,..."

if [ -n "$SECONDARY_IPS" ]; then
    echo "Adding secondary IPs..."
    IFS=',' read -ra IPS <<< "$SECONDARY_IPS"
    for ip in "${IPS[@]}"; do
        ip=$(echo "$ip" | xargs)  # trim whitespace
        echo "  Adding $ip to eth0"
        ip addr add "$ip" dev eth0 2>/dev/null || echo "  Warning: $ip may already be assigned"
    done
    # Give the kernel a moment to register the addresses
    sleep 1
fi

echo "Starting ONVIF Splitter..."
exec python -m onvif_splitter "$@"
