"""Known homelab hosts and services."""

NETWORK = "192.168.1.0/24"

# Proxmox hosts
PROXMOX_HOST1 = "192.168.1.75"
PVE = "192.168.1.74"

# VMs / services
HOME_ASSISTANT = "192.168.1.73"
GRAFANA_HOST = "192.168.1.48"
FRIGATE_HOST = "192.168.1.47"
ZIGBEE2MQTT_V1 = "192.168.1.71"
FALCON_PLAYER = "192.168.1.66"

# Service endpoints
GRAFANA_URL = f"http://{GRAFANA_HOST}:3000"
LOKI_URL = f"http://{GRAFANA_HOST}:3100"
HOME_ASSISTANT_URL = f"http://{HOME_ASSISTANT}:8123"
FRIGATE_URL = f"http://{FRIGATE_HOST}:5000"

# Named host map — useful for scanning / reporting
KNOWN_HOSTS = {
    PROXMOX_HOST1:  "proxmox-host1",
    PVE:            "pve",
    HOME_ASSISTANT: "home-assistant",
    GRAFANA_HOST:   "grafana+prometheus+loki",
    FRIGATE_HOST:   "frigate",
    ZIGBEE2MQTT_V1: "zigbee2mqtt-v1",
    FALCON_PLAYER:  "falcon-player",
}

# LXC / VM inventory (for reference, not directly reachable by IP unless assigned)
GUESTS = {
    "proxmox-host1": [
        {"id": 101, "type": "LXC", "service": "influxdb"},
        {"id": 102, "type": "LXC", "service": "zigbee2mqtt-v2"},
        {"id": 103, "type": "VM",  "service": "home-assistant", "ip": HOME_ASSISTANT},
        {"id": 104, "type": "VM",  "service": "grafana+prometheus+loki", "ip": GRAFANA_HOST},
        {"id": 105, "type": "LXC", "service": "unifi-controller"},
        {"id": 107, "type": "LXC", "service": "docker-wyze-bridge"},
        {"id": 108, "type": "VM",  "service": "frigate", "ip": FRIGATE_HOST},
    ],
    "pve": [
        {"id": 101, "type": "LXC", "service": "mqtt-broker"},
        {"id": 106, "type": "LXC", "service": "zigbee2mqtt-v1", "ip": ZIGBEE2MQTT_V1},
        {"id": 107, "type": "LXC", "service": "proxmox-backup-server"},
    ],
}
