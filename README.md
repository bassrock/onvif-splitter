# ONVIF Splitter

Split a multi-channel NVR into individual virtual ONVIF cameras. Each NVR channel gets its own IP address, MAC address, and fully functional ONVIF device — discoverable by UniFi Protect, Scrypted, Frigate, Home Assistant, or any ONVIF-compatible software.

## Features

- **Virtual ONVIF cameras** — each NVR channel appears as an independent device on the network
- **Unique MAC addresses** — each camera gets its own MAC (required by UniFi Protect)
- **RTSP proxy** — transparent TCP proxy so streams appear to come from the virtual camera's IP
- **Snapshot proxy** — fetches snapshots from the NVR with proper HTTP Digest auth
- **Motion events** — ONVIF PullPoint events from NVR, demuxed per channel
- **WS-Discovery** — cameras auto-discoverable on the network
- **Two deployment options** — Docker containers or native binary on UniFi OS

## Supported NVRs

Tested with Dahua and Dahua OEM NVRs. Should work with any NVR that supports:

- ONVIF Profile S (media streaming)
- ONVIF PullPoint event subscriptions
- Per-channel RTSP streams (`/cam/realmonitor?channel=N&subtype=0`)

Falls back to the Dahua HTTP event API (`/cgi-bin/eventManager.cgi`) if ONVIF PullPoint fails.

---

## Deployment Options

### Option A: Native Binary on UniFi OS (Recommended for UniFi Protect)

A single Go binary (~6.5MB) runs directly on UDM Pro, UDM SE, or UDR as a systemd service. Creates veth pairs bridged into `br0` with unique MACs — the cleanest setup for UniFi Protect.

```
UniFi OS (UDM/UDR)
├── veth pairs bridged into br0:
│   ├── cam1  (192.168.1.121, MAC 00:1F:54:A1:B2:01)
│   ├── cam2  (192.168.1.122, MAC 00:1F:54:A1:B2:02)
│   └── ...
│
└── onvif-splitter-arm64 (single process)
    ├── 1 ONVIF server per camera IP
    ├── 1 RTSP proxy per camera (port 554)
    ├── 1 WS-Discovery per camera
    └── 1 shared NVR event subscription
```

#### Install

```bash
ssh root@<your-unifi-ip>

# Download binary
curl -sL https://github.com/bassrock/onvif-splitter/releases/latest/download/onvif-splitter-linux-arm64 \
  -o /data/onvif-splitter-arm64
chmod +x /data/onvif-splitter-arm64
```

Create config at `/data/config.yaml`:

```yaml
nvr:
  host: 192.168.1.238
  port: 80
  rtsp_port: 554
  username: admin
  password: your-password-here

onvif_port: 8000  # Use 8000 since 8080 is taken by UniFi controller

channels:
  - channel: 1
    ip: 192.168.1.121
    name: "Camera 1"
    mac: "00:1F:54:A1:B2:01"
  - channel: 2
    ip: 192.168.1.122
    name: "Camera 2"
    mac: "00:1F:54:A1:B2:02"
  # Add more channels as needed
```

Create network interface setup at `/data/setup-interfaces.sh`:

```bash
#!/bin/bash
BRIDGE="br0"

CAMERAS=(
    "cam1  192.168.1.121/24  00:1F:54:A1:B2:01"
    "cam2  192.168.1.122/24  00:1F:54:A1:B2:02"
    # Match your config.yaml channels
)

for entry in "${CAMERAS[@]}"; do
    read -r NAME IP MAC <<< "$entry"
    BR_END="${NAME}-br"
    if ip link show "$NAME" &>/dev/null; then continue; fi
    echo "Creating $NAME: IP=$IP MAC=$MAC"
    ip link add "$BR_END" type veth peer name "$NAME"
    ip link set "$BR_END" master "$BRIDGE"
    ip link set "$BR_END" up
    ip link set "$NAME" address "$MAC"
    ip addr add "$IP" dev "$NAME"
    ip link set "$NAME" up
done
```

```bash
chmod +x /data/setup-interfaces.sh
```

Install systemd service:

```bash
cat > /etc/systemd/system/onvif-splitter.service << 'EOF'
[Unit]
Description=ONVIF Splitter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/data/setup-interfaces.sh
ExecStart=/data/onvif-splitter-arm64 -config /data/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now onvif-splitter
```

Check logs: `journalctl -u onvif-splitter -f`

#### Why veth pairs instead of macvlan?

macvlan interfaces have parent-child isolation — the host process (UniFi Protect) can't see the macvlan children's unique MACs. veth pairs bridged into br0 solve this: each camera's MAC is visible in the bridge forwarding database and fully reachable from the host.

#### Port note

Use `onvif_port: 8000` (not 8080) on UniFi OS since the UniFi controller occupies port 8080.

---

### Option B: Docker — Multi-Container with Coordinator

One container per camera (for unique Docker-level MACs) plus a coordinator container that shares a single NVR event subscription.

```
┌─ coordinator ────────────────────────────────┐
│  1 NVR PullPoint subscription                │
│  Pushes events to camera containers via HTTP │
└──────────────────────────────────────────────┘
     │ POST /internal/event
     ├──→ cameras-channel3 (unique MAC + IP)
     ├──→ cameras-channel4 (unique MAC + IP)
     └──→ ...
```

#### Docker Compose (Portainer)

```yaml
x-common: &common
  image: ghcr.io/bassrock/onvif-splitter:main
  restart: unless-stopped
  environment: &common-env
    NVR_HOST: 192.168.2.253
    NVR_PORT: 80
    NVR_RTSP_PORT: 554
    NVR_USERNAME: admin
    NVR_PASSWORD: changeme
    ONVIF_PORT: 8080
    COORDINATOR_URL: "true"  # Tells cameras to skip NVR event subscription

services:
  coordinator:
    image: ghcr.io/bassrock/onvif-splitter:main
    container_name: cameras-coordinator
    restart: unless-stopped
    environment:
      NVR_HOST: 192.168.2.253
      NVR_PORT: 80
      NVR_RTSP_PORT: 554
      NVR_USERNAME: admin
      NVR_PASSWORD: changeme
      ONVIF_PORT: 8080
      MODE: coordinator
      CHANNELS: >-
        3|192.168.2.123|Camera 3,
        4|192.168.2.124|Camera 4,
        5|192.168.2.125|Camera 5
    networks:
      cameras:
        ipv4_address: 192.168.2.120

  channel3:
    <<: *common
    container_name: cameras-channel3
    mac_address: "02:42:c0:a8:02:7b"
    environment:
      <<: *common-env
      CHANNELS: "3|192.168.2.123|Camera 3|02:42:c0:a8:02:7b"
    networks:
      cameras:
        ipv4_address: 192.168.2.123

  # Repeat for each channel...

networks:
  cameras:
    external: true
    name: your-macvlan-network
```

#### Environment Variable Config

The Docker image supports inline config via environment variables — no config file needed:

| Variable | Description | Default |
|----------|-------------|---------|
| `NVR_HOST` | NVR IP address | *required* |
| `NVR_PORT` | NVR HTTP port | `80` |
| `NVR_RTSP_PORT` | NVR RTSP port | `554` |
| `NVR_USERNAME` | NVR username | `admin` |
| `NVR_PASSWORD` | NVR password | *required* |
| `ONVIF_PORT` | ONVIF service port | `8080` |
| `CHANNELS` | Pipe-delimited: `channel\|ip\|name\|mac` | *required* |
| `MODE` | Set to `coordinator` for event broker | (camera mode) |
| `COORDINATOR_URL` | Any value skips NVR event subscription | (unset) |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` | `INFO` |

#### Why multi-container?

UniFi Protect identifies cameras by MAC address. Docker macvlan gives each container a real unique MAC on the network. A single container with secondary IPs shares one MAC, which causes cameras to swap identities in Protect.

#### Network requirements

- **macvlan** requires a Linux host with ethernet (doesn't work on Docker Desktop or WiFi)
- **ipvlan** works over WiFi but shares the host MAC (cameras swap in Protect)
- The macvlan Docker network must already exist or be defined in the compose

---

### Option C: Docker — Single Container (non-Protect)

If your ONVIF consumer doesn't require unique MACs (Scrypted, Frigate, Home Assistant), a single container is simpler:

```yaml
services:
  onvif-splitter:
    image: ghcr.io/bassrock/onvif-splitter:main
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
    environment:
      NVR_HOST: 192.168.2.253
      NVR_PASSWORD: changeme
      ONVIF_PORT: 8080
      CHANNELS: >-
        1|192.168.2.161|Camera 1,
        2|192.168.2.162|Camera 2,
        3|192.168.2.163|Camera 3
      SECONDARY_IPS: "192.168.2.162/24,192.168.2.163/24"
    networks:
      cameras:
        ipv4_address: 192.168.2.161

networks:
  cameras:
    driver: macvlan
    driver_opts:
      parent: eth0
    ipam:
      config:
        - subnet: 192.168.2.0/24
          gateway: 192.168.2.1
```

All cameras share one MAC but have unique IPs. One NVR event subscription, events demuxed in-memory.

---

## YAML Config Reference

```yaml
nvr:
  host: 192.168.2.253      # NVR IP address (required)
  port: 80                  # NVR HTTP port (default: 80)
  rtsp_port: 554            # NVR RTSP port (default: 554)
  username: admin           # NVR username (default: admin)
  password: changeme        # NVR password (required)

onvif_port: 8080            # Port for virtual ONVIF services (default: 8080)

channels:
  - channel: 1              # NVR channel number, 1-based (required)
    ip: 192.168.2.121       # Virtual camera IP (required)
    name: "Front Door"      # Display name (default: Camera N)
    mac: "00:1F:54:A1:B2:01"  # MAC address for ONVIF reporting (optional)
    port: 8080              # Per-channel port override (optional)
```

## How Events Work

1. The splitter creates a single ONVIF PullPoint subscription to the NVR
2. The NVR reports motion events with a `VideoSourceConfigurationToken` identifying the channel
3. The splitter demuxes events and pushes them to the correct virtual camera's event queue
4. When a consumer calls `PullMessages` on a virtual camera, it receives only that camera's events

If the ONVIF PullPoint subscription fails (e.g., MaxPullPoints limit reached), the splitter falls back to the Dahua HTTP event API (`/cgi-bin/eventManager.cgi`).

## How RTSP Works

Each virtual camera runs a TCP proxy on port 554. When a consumer connects to `rtsp://camera-ip:554/...`, the proxy forwards the TCP connection to the NVR. No transcoding — just byte-level forwarding. The NVR handles RTSP authentication and streaming based on the channel in the request path.

## Building

### Go binary (for UniFi OS)

```bash
# Native
go build -o onvif-splitter ./cmd/onvif-splitter/

# Cross-compile for ARM64 (UDM/UDR)
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -ldflags="-s -w" \
  -o onvif-splitter-arm64 ./cmd/onvif-splitter/
```

### Docker image

```bash
docker compose build
```

### Python (development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m onvif_splitter config.yaml
```

## Architecture

The project has two implementations:

- **Go** (`cmd/`, `internal/`) — single static binary, used for UniFi OS native deployment and CI-built releases
- **Python** (`onvif_splitter/`) — used in Docker image, supports coordinator mode for multi-container setups

Both implement the same ONVIF virtual device functionality.

## License

MIT
