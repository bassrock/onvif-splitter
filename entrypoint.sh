#!/bin/bash
set -e

# Only create macvlan subinterfaces if there are multiple channels.
# In multi-container mode, each container has one channel and gets
# its MAC/IP from Docker — no macvlan setup needed.

if [ -n "$CHANNELS" ]; then
    IFS=',' read -ra ENTRIES <<< "$CHANNELS"
    COUNT=${#ENTRIES[@]}

    if [ "$COUNT" -gt 1 ]; then
        FIRST=true
        for entry in "${ENTRIES[@]}"; do
            entry=$(echo "$entry" | xargs)
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
fi

echo "Starting ONVIF Splitter..."
exec python -m onvif_splitter "$@"
