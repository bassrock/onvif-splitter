# ONVIF Splitter

Split a multi-channel NVR into individual virtual ONVIF cameras. Each NVR channel gets its own IP address and fully functional ONVIF device — discoverable by UniFi Protect, Scrypted, Frigate, Home Assistant, or any ONVIF-compatible software.

## How it works

```
┌──────────────────── Single Docker Container ────────────────────┐
│                                                                  │
│  NVR Event Subscriber ── 1 ONVIF PullPoint subscription ──→ NVR │
│       │ demux by channel                                         │
│       ├──→ Virtual Camera 1 @ 192.168.2.161                     │
│       ├──→ Virtual Camera 2 @ 192.168.2.162                     │
│       ├──→ ...                                                   │
│       └──→ Virtual Camera 8 @ 192.168.2.168                     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

A single container runs on a Docker macvlan network with secondary IPs — one per camera channel. Each virtual camera serves:

- **ONVIF Device/Media/Events services** on its own IP
- **WS-Discovery** so cameras are auto-discoverable on the network
- **RTSP stream URIs** pointing directly to the NVR (no transcoding or proxying)
- **Snapshot proxy** through each virtual camera's IP
- **Motion events** via ONVIF PullPoint, sourced from the NVR's single shared subscription

## Supported NVRs

Tested with Dahua and Dahua OEM NVRs. Should work with any NVR that supports:

- ONVIF Profile S (media streaming)
- ONVIF PullPoint event subscriptions
- Per-channel RTSP streams

Falls back to the Dahua HTTP event API (`/cgi-bin/eventManager.cgi`) if ONVIF PullPoint fails.

## Quick Start

### 1. Configure

Copy and edit the config file:

```bash
cp config.yaml config.local.yaml
```

```yaml
nvr:
  host: 192.168.2.253
  port: 80
  rtsp_port: 554
  username: admin
  password: your-password-here

onvif_port: 8080

channels:
  - channel: 1
    ip: 192.168.2.161
    name: "Front Door"
  - channel: 2
    ip: 192.168.2.162
    name: "Backyard"
  # Add as many channels as your NVR has
```

> **Important:** Choose IPs that are free on your network and outside your DHCP range.

### 2. Configure Docker networking

Edit `docker-compose.yml`:

- Change `parent: eth0` to your host's network interface (run `ip link` to find it)
- Set the primary IP (`ipv4_address`) and secondary IPs (`SECONDARY_IPS`) to match your config
- Set the correct subnet and gateway for your network

```yaml
services:
  onvif-splitter:
    image: ghcr.io/bassrock/onvif-splitter:main
    container_name: onvif-splitter
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
    environment:
      SECONDARY_IPS: "192.168.2.162/24,192.168.2.163/24,192.168.2.164/24,192.168.2.165/24,192.168.2.166/24,192.168.2.167/24,192.168.2.168/24"
    volumes:
      - ./config.local.yaml:/app/config.yaml:ro
    networks:
      cameras:
        ipv4_address: 192.168.2.161

networks:
  cameras:
    driver: macvlan
    driver_opts:
      parent: eth0  # Your host's network interface
    ipam:
      config:
        - subnet: 192.168.2.0/24
          gateway: 192.168.2.1
```

### 3. Run

```bash
docker compose up -d
```

### 4. Add cameras

In your ONVIF client (UniFi Protect, Scrypted, etc.), add each virtual camera by IP:

| Camera | IP | ONVIF Port |
|--------|-----|------------|
| Camera 1 | 192.168.2.161 | 8080 |
| Camera 2 | 192.168.2.162 | 8080 |
| ... | ... | 8080 |

Use the same username/password as your NVR.

## Building from source

```bash
docker compose build
docker compose up -d
```

Or run locally for development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m onvif_splitter config.yaml
```

## Configuration Reference

| Field | Description | Default |
|-------|-------------|---------|
| `nvr.host` | NVR IP address | *required* |
| `nvr.port` | NVR HTTP port | `80` |
| `nvr.rtsp_port` | NVR RTSP port | `554` |
| `nvr.username` | NVR username | `admin` |
| `nvr.password` | NVR password | *required* |
| `onvif_port` | Port for virtual ONVIF services | `8080` |
| `channels[].channel` | NVR channel number (1-based) | *required* |
| `channels[].ip` | IP address for this virtual camera | *required* |
| `channels[].name` | Display name for the camera | `Camera N` |

## How events work

The splitter creates a single ONVIF PullPoint subscription to the NVR. When motion is detected on any channel, the NVR reports it with a `VideoSourceConfigurationToken` identifying the channel. The splitter demuxes this and pushes the event to the correct virtual camera's event queue. When a consumer (UniFi Protect, etc.) calls `PullMessages` on a virtual camera, it receives only that camera's events.

If the ONVIF PullPoint subscription fails (e.g., the NVR's `MaxPullPoints` limit is reached), the splitter falls back to the Dahua HTTP event API, which has no connection limits.

## Requirements

- **Linux host** with Docker (macvlan networking doesn't work on Docker Desktop for Mac/Windows)
- NVR accessible on the same network
- Free IP addresses for each virtual camera

## License

MIT
