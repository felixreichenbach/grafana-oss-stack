#!/usr/bin/env bash
set -euo pipefail

HOST="127.0.0.1"
PORT="514"
PROTO="udp"
FORMAT="rfc3164"
COUNT="12"
INTERVAL="0.25"
RUN_ID="meraki-sim-$(date +%s)"

usage() {
  cat <<'EOF'
Meraki Syslog Simulator

Usage:
  ./scripts/meraki-syslog-sim.sh [options]

Options:
  --host <host>          Destination host (default: 127.0.0.1)
  --port <port>          Destination port (default: 1514)
  --proto <udp|tcp>      Transport protocol (default: udp)
  --format <rfc3164|rfc5424>
                         Syslog wire format (default: rfc3164)
  --count <n>            Number of events to send (default: 12)
  --interval <seconds>   Delay between events (default: 0.25)
  --run-id <id>          Marker value to correlate a test run
  -h, --help             Show help

Examples:
  ./scripts/meraki-syslog-sim.sh
  ./scripts/meraki-syslog-sim.sh --count 20 --run-id demo-001
  ./scripts/meraki-syslog-sim.sh --format rfc3164 --run-id demo-3164
  ./scripts/meraki-syslog-sim.sh --proto tcp --port 1514
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --proto)
      PROTO="${2:-}"
      shift 2
      ;;
    --format)
      FORMAT="${2:-}"
      shift 2
      ;;
    --count)
      COUNT="${2:-}"
      shift 2
      ;;
    --interval)
      INTERVAL="${2:-}"
      shift 2
      ;;
    --run-id)
      RUN_ID="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$PROTO" != "udp" && "$PROTO" != "tcp" ]]; then
  echo "--proto must be udp or tcp" >&2
  exit 1
fi

if [[ "$FORMAT" != "rfc3164" && "$FORMAT" != "rfc5424" ]]; then
  echo "--format must be rfc3164 or rfc5424" >&2
  exit 1
fi

if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [[ "$COUNT" -lt 1 ]]; then
  echo "--count must be a positive integer" >&2
  exit 1
fi

send_line() {
  local line="$1"
  if [[ "$PROTO" == "udp" ]]; then
    printf '%s\n' "$line" | nc -u -w 1 "$HOST" "$PORT"
  else
    printf '%s\n' "$line" | nc -w 1 "$HOST" "$PORT"
  fi
}

echo "Sending $COUNT Meraki-like syslog events to $HOST:$PORT over $PROTO ($FORMAT)"
echo "Run marker: $RUN_ID"

for ((i=1; i<=COUNT; i++)); do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  octet="$(printf '%d' $(( (i % 250) + 1 )))"

  case $((i % 4)) in
    0)
      app="ids-alerted"
      msg="src=10.0.10.${octet} dst=8.8.8.8 protocol=tcp sport=$((50000+i)) dport=443 action=allow signature=ET_POLICY marker=${RUN_ID} event=${i}"
      ;;
    1)
      app="flows"
      msg="src=10.0.20.${octet} dst=1.1.1.1 protocol=udp sport=$((40000+i)) dport=53 action=allow bytes=$((1200+i*3)) marker=${RUN_ID} event=${i}"
      ;;
    2)
      app="dhcp"
      msg="client_mac=aa:bb:cc:dd:ee:$(printf '%02x' "$octet") assigned_ip=10.0.30.${octet} vlan=30 lease_seconds=86400 marker=${RUN_ID} event=${i}"
      ;;
    3)
      app="vpn_connect"
      msg="peer=branch-${octet} local_subnet=10.0.${octet}.0/24 remote_subnet=10.200.${octet}.0/24 status=up marker=${RUN_ID} event=${i}"
      ;;
  esac

  if [[ "$FORMAT" == "rfc3164" ]]; then
    ts3164="$(date -u +'%b %e %T')"
    line="<134>${ts3164} MX68 ${app}[1001]: ${msg}"
  else
    line="<134>1 ${ts} MX68 ${app} 1001 security_event [meta vendor=\"meraki\" product=\"mx\" network=\"branch-01\"] ${msg}"
  fi

  send_line "$line"
  sleep "$INTERVAL"
done

echo "Done. Query Loki with: {job=\"meraki-syslog\"} |= \"${RUN_ID}\""
