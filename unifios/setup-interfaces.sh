#!/bin/bash
# Create macvlan interfaces for virtual ONVIF cameras.
# Edit the CAMERAS array below to match your config.yaml.
#
# Each entry: "interface_name ip_address mac_address parent_interface"
# The parent_interface should be the VLAN interface your NVR is on.
# Run "ip link" to find available interfaces (e.g., br0, br1, eth0, br0.1)

PARENT="br0"  # Change to match your network interface

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

    # Skip if already exists
    if ip link show "$NAME" &>/dev/null; then
        echo "Interface $NAME already exists, skipping"
        continue
    fi

    echo "Creating $NAME: IP=$IP MAC=$MAC on $PARENT"
    ip link add "$NAME" link "$PARENT" type macvlan mode bridge
    ip link set "$NAME" address "$MAC"
    ip addr add "$IP" dev "$NAME"
    ip link set "$NAME" up
done

echo "Interfaces ready"
