#!/bin/bash
set -e

# Create macvlan subinterfaces for each camera channel.
# Each gets its own MAC and IP so it appears as a separate device on the network.
#
# CHANNELS env format: channel|ip|name|mac,...
# The first channel uses the container's primary interface (eth0).
# Remaining channels get macvlan subinterfaces.

if [ -n "$CHANNELS" ]; then
    FIRST=true
    IFS=',' read -ra ENTRIES <<< "$CHANNELS"
    for entry in "${ENTRIES[@]}"; do
        entry=$(echo "$entry" | xargs)  # trim whitespace
        [ -z "$entry" ] && continue

        IFS='|' read -r CH IP NAME MAC <<< "$entry"

        if [ "$FIRST" = true ]; then
            echo "Primary interface: $IP (channel $CH)"
            FIRST=false
            continue
        fi

        IFACE="cam${CH}"
        echo "Creating macvlan $IFACE: IP=$IP MAC=${MAC:-auto}"
        ip link add "$IFACE" link eth0 type macvlan mode bridge
        [ -n "$MAC" ] && ip link set "$IFACE" address "$MAC"
        ip addr add "${IP}/24" dev "$IFACE"
        ip link set "$IFACE" up
    done
    sleep 1
fi

echo "Starting ONVIF Splitter..."
exec python -m onvif_splitter "$@"
