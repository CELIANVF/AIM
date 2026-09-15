#!/usr/bin/env bash
# Routage Internet via WiFi (passerelle 192.168.1.1 sur le réseau WiFi).
# Nécessaire car Ethernet et WiFi partagent le même sous-réseau 192.168.1.0/24
# avec la même IP de passerelle sur deux réseaux L2 distincts.
#
# Usage sur spam :
#   sudo bash ~/AIM/scripts/setup-wifi-internet.sh

set -euo pipefail

ETH_DEV="enp0s31f6"
WIFI_DEV="wlp2s0"
ETH_IP="192.168.1.150"
WIFI_IP="192.168.1.87"
GW="192.168.1.1"
# MAC de l'AP WiFi (joignable sur wlp2s0) — requis car 192.168.1.1 ne répond pas en ARP sur WiFi
WIFI_GW_MAC="c4:ea:1d:ee:f5:c2"

ETH_TABLE=100
WIFI_TABLE=101

if [[ "${EUID:-0}" -ne 0 ]]; then
    echo "Exécuter avec sudo." >&2
    exit 1
fi

echo "→ Entrée ARP statique : ${GW} → ${WIFI_GW_MAC} sur ${WIFI_DEV}"
ip neigh replace "${GW}" lladdr "${WIFI_GW_MAC}" dev "${WIFI_DEV}" nored permanent

echo "→ Routage par politique (table ${WIFI_TABLE} pour ${WIFI_IP})"
ip route flush table "${WIFI_TABLE}" 2>/dev/null || true
ip route add 192.168.1.0/24 dev "${WIFI_DEV}" scope link table "${WIFI_TABLE}"
ip route add default via "${GW}" dev "${WIFI_DEV}" table "${WIFI_TABLE}"

ip rule del from "${WIFI_IP}" lookup "${WIFI_TABLE}" 2>/dev/null || true
ip rule add from "${WIFI_IP}" lookup "${WIFI_TABLE}" priority 100

echo "→ Routage par politique (table ${ETH_TABLE} pour ${ETH_IP})"
ip route flush table "${ETH_TABLE}" 2>/dev/null || true
ip route add 192.168.1.0/24 dev "${ETH_DEV}" scope link table "${ETH_TABLE}"
ip route add default via "${GW}" dev "${ETH_DEV}" table "${ETH_TABLE}"

ip rule del from "${ETH_IP}" lookup "${ETH_TABLE}" 2>/dev/null || true
ip rule add from "${ETH_IP}" lookup "${ETH_TABLE}" priority 100

echo "→ Netplan persistant"
install -d /etc/netplan
cat > /etc/netplan/00-installer-config.yaml <<EOF
network:
  version: 2
  renderer: networkd
  ethernets:
    ${ETH_DEV}:
      dhcp4: false
      addresses:
        - ${ETH_IP}/24
      routes:
        - to: default
          via: ${GW}
          metric: 100
        - to: default
          via: ${GW}
          table: ${ETH_TABLE}
      routing-policy:
        - from: ${ETH_IP}
          table: ${ETH_TABLE}
          priority: 100
EOF

cat > /etc/netplan/00-installer-config-wifi.yaml <<EOF
network:
  version: 2
  renderer: networkd
  ethernets:
    ${WIFI_DEV}:
      dhcp4: false
      addresses:
        - ${WIFI_IP}/24
      routes:
        - to: default
          via: ${GW}
          metric: 200
        - to: default
          via: ${GW}
          table: ${WIFI_TABLE}
      routing-policy:
        - from: ${WIFI_IP}
          table: ${WIFI_TABLE}
          priority: 100
EOF

install -d /etc/systemd/network
cat > /etc/systemd/network/10-wlp2s0-wifi-gw.network <<EOF
[Match]
Name=${WIFI_DEV}

[Neighbor]
Address=${GW}
LinkAddress=${WIFI_GW_MAC}
EOF

chmod 600 /etc/netplan/*.yaml

echo "→ Application netplan"
netplan apply

echo ""
echo "Tests :"
ping -c 2 -W 2 -I "${WIFI_DEV}" "${GW}" || true
ping -c 2 -W 2 -I "${WIFI_DEV}" 8.8.8.8 || true
ping -c 2 -W 2 -I "${ETH_DEV}" 8.8.8.8 || true
ip route get 8.8.8.8 from "${WIFI_IP}" iif lo
