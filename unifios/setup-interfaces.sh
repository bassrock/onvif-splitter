#!/bin/bash
# Create veth pairs for virtual ONVIF cameras.
# Each camera gets a veth pair: one end bridged into br0 (visible to Protect),
# the other end with the camera's IP and unique MAC.

BRIDGE="br0"

CAMERAS=(
    "cam1  192.168.1.121/24  00:1F:54:A1:B2:01"
    "cam2  192.168.1.122/24  00:1F:54:A1:B2:02"
    "cam4  192.168.1.124/24  00:1F:54:A1:B2:04"
    "cam7  192.168.1.127/24  00:1F:54:A1:B2:07"
    "cam8  192.168.1.128/24  00:1F:54:A1:B2:08"
    "cam11 192.168.1.131/24  00:1F:54:A1:B2:0B"
)

for entry in "${CAMERAS[@]}"; do
    read -r NAME IP MAC <<< "$entry"
    BR_END="${NAME}-br"

    if ip link show "$NAME" &>/dev/null; then
        echo "Interface $NAME already exists, skipping"
        continue
    fi

    echo "Creating $NAME: IP=$IP MAC=$MAC (bridged to $BRIDGE)"
    ip link add "$BR_END" type veth peer name "$NAME"
    ip link set "$BR_END" master "$BRIDGE"
    ip link set "$BR_END" up
    ip link set "$NAME" address "$MAC"
    ip addr add "$IP" dev "$NAME"
    ip link set "$NAME" up
done

echo "Interfaces ready"
