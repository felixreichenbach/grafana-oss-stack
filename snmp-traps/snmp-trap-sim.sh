#!/usr/bin/env bash
set -euo pipefail

HOST="127.0.0.1"
PORT="162"
COMMUNITY="public"
COUNT="1"
COUNT_SET="0"
INTERVAL="1"
RUN_ID="snmp-trap-sim-$(date +%s)"
DEVICE="router-lab-01"
LOCATION="lab-rack-a"
TRAP_OID=".1.3.6.1.6.3.1.1.5.1"
PROFILE="link-down"

usage() {
  cat <<'EOF'
SNMP Trap Simulator

Usage:
  ./snmp-traps/snmp-trap-sim.sh [options]

Options:
  --host <host>          Destination host (default: 127.0.0.1)
  --port <port>          Destination UDP port (default: 162)
  --community <name>     SNMP community (default: public)
  --count <n>            Number of traps to send (default: 1)
  --interval <seconds>   Delay between traps (default: 1)
  --run-id <id>          Marker value to correlate a test run
  --device <name>        Device name to place in sysName.0
  --location <name>      Device location to place in sysLocation.0
  --profile <name>       Trap profile: link-down, power-loss, or power-restored
  --trap-oid <oid>       Notification OID (default: coldStart)
  -h, --help             Show help

Examples:
  ./snmp-traps/snmp-trap-sim.sh
  ./snmp-traps/snmp-trap-sim.sh --count 3 --run-id demo-traps-001
  ./snmp-traps/snmp-trap-sim.sh --profile power-loss --run-id demo-power-001
  ./snmp-traps/snmp-trap-sim.sh --profile power-restored --run-id demo-restore-001
  ./snmp-traps/snmp-trap-sim.sh --host 192.0.2.10 --port 162
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
    --community)
      COMMUNITY="${2:-}"
      shift 2
      ;;
    --count)
      COUNT="${2:-}"
      COUNT_SET="1"
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
    --device)
      DEVICE="${2:-}"
      shift 2
      ;;
    --location)
      LOCATION="${2:-}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:-}"
      shift 2
      ;;
    --trap-oid)
      TRAP_OID="${2:-}"
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

if ! command -v snmptrap >/dev/null 2>&1; then
  echo "snmptrap command not found. Install net-snmp to use this generator." >&2
  exit 1
fi

if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [[ "$COUNT" -lt 1 ]]; then
  echo "--count must be a positive integer" >&2
  exit 1
fi

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [[ "$PORT" -lt 1 ]] || [[ "$PORT" -gt 65535 ]]; then
  echo "--port must be an integer between 1 and 65535" >&2
  exit 1
fi

if [[ "$PROFILE" != "link-down" && "$PROFILE" != "power-loss" && "$PROFILE" != "power-restored" ]]; then
  echo "--profile must be link-down, power-loss, or power-restored" >&2
  exit 1
fi

if [[ "$PROFILE" == "power-loss" && "$COUNT_SET" == "0" ]]; then
  COUNT="3"
fi

if [[ "$PROFILE" == "power-restored" && "$COUNT_SET" == "0" ]]; then
  COUNT="2"
fi

send_default_trap() {
  local sequence="$1"
  local description="run_id=${RUN_ID} event=${sequence} severity=warning interface=xe-0/0/${sequence} status=linkDown"

  snmptrap -v 2c -c "$COMMUNITY" "$HOST:$PORT" '' "$TRAP_OID" \
    .1.3.6.1.2.1.1.5.0 s "$DEVICE" \
    .1.3.6.1.2.1.1.6.0 s "$LOCATION" \
    .1.3.6.1.2.1.1.1.0 s "$description"
}

send_power_loss_trap() {
  local sequence="$1"
  local stage_index="$(( (sequence - 1) % 3 ))"
  local stage_name=""
  local stage_trap_oid=""
  local battery_percent=""
  local runtime_minutes=""
  local seconds_on_battery=""
  local input_voltage=""
  local output_source="5"
  local severity="critical"
  local description=""

  case "$stage_index" in
    0)
      stage_name="utilityPowerLost"
      stage_trap_oid=".1.3.6.1.2.1.33.2.0.1"
      battery_percent="100"
      runtime_minutes="15"
      seconds_on_battery="5"
      input_voltage="0"
      ;;
    1)
      stage_name="lowBattery"
      stage_trap_oid=".1.3.6.1.2.1.33.2.0.3"
      battery_percent="22"
      runtime_minutes="4"
      seconds_on_battery="420"
      input_voltage="0"
      ;;
    2)
      stage_name="shutdownImminent"
      stage_trap_oid=".1.3.6.1.2.1.33.2.0.3"
      battery_percent="8"
      runtime_minutes="1"
      seconds_on_battery="840"
      input_voltage="0"
      ;;
  esac

  description="run_id=${RUN_ID} event=${sequence} profile=power-loss stage=${stage_name} severity=${severity} utility=lost battery_pct=${battery_percent} runtime_min=${runtime_minutes} input_v=${input_voltage} output_source=battery load_pct=42 alarm=audible"

  snmptrap -v 2c -c "$COMMUNITY" "$HOST:$PORT" '' "$stage_trap_oid" \
    .1.3.6.1.2.1.1.5.0 s "$DEVICE" \
    .1.3.6.1.2.1.1.6.0 s "$LOCATION" \
    .1.3.6.1.2.1.1.1.0 s "$description" \
    .1.3.6.1.2.1.33.1.2.3.0 i "$runtime_minutes" \
    .1.3.6.1.2.1.33.1.2.2.0 i "$seconds_on_battery" \
    .1.3.6.1.2.1.33.1.2.4.0 i "$battery_percent" \
    .1.3.6.1.2.1.33.1.3.3.1.3.1 i "$input_voltage" \
    .1.3.6.1.2.1.33.1.4.1.0 i "$output_source" \
    .1.3.6.1.2.1.33.1.4.4.1.5.1 i 42
}

send_power_restored_trap() {
  local sequence="$1"
  local stage_index="$(( (sequence - 1) % 2 ))"
  local stage_name=""
  local alarm_id=""
  local alarm_descr_oid=""
  local battery_percent=""
  local runtime_minutes=""
  local input_voltage="230"
  local output_source="3"
  local severity="info"
  local description=""

  case "$stage_index" in
    0)
      stage_name="utilityPowerRestored"
      alarm_id="102"
      alarm_descr_oid=".1.3.6.1.2.1.33.1.6.3.2"
      battery_percent="24"
      runtime_minutes="9"
      ;;
    1)
      stage_name="lowBatteryCleared"
      alarm_id="103"
      alarm_descr_oid=".1.3.6.1.2.1.33.1.6.3.3"
      battery_percent="31"
      runtime_minutes="14"
      ;;
  esac

  description="run_id=${RUN_ID} event=${sequence} profile=power-restored stage=${stage_name} severity=${severity} utility=restored battery_pct=${battery_percent} runtime_min=${runtime_minutes} input_v=${input_voltage} output_source=normal load_pct=38 alarm=cleared"

  snmptrap -v 2c -c "$COMMUNITY" "$HOST:$PORT" '' '.1.3.6.1.2.1.33.2.0.4' \
    .1.3.6.1.2.1.1.5.0 s "$DEVICE" \
    .1.3.6.1.2.1.1.6.0 s "$LOCATION" \
    .1.3.6.1.2.1.1.1.0 s "$description" \
    .1.3.6.1.2.1.33.1.6.2.1.1.$alarm_id i "$alarm_id" \
    .1.3.6.1.2.1.33.1.6.2.1.2.$alarm_id o "$alarm_descr_oid" \
    .1.3.6.1.2.1.33.1.2.3.0 i "$runtime_minutes" \
    .1.3.6.1.2.1.33.1.2.2.0 i 0 \
    .1.3.6.1.2.1.33.1.2.4.0 i "$battery_percent" \
    .1.3.6.1.2.1.33.1.3.3.1.3.1 i "$input_voltage" \
    .1.3.6.1.2.1.33.1.4.1.0 i "$output_source" \
    .1.3.6.1.2.1.33.1.4.4.1.5.1 i 38
}

send_trap() {
  local sequence="$1"
  if [[ "$PROFILE" == "power-loss" ]]; then
    send_power_loss_trap "$sequence"
  elif [[ "$PROFILE" == "power-restored" ]]; then
    send_power_restored_trap "$sequence"
  else
    send_default_trap "$sequence"
  fi
}

echo "Sending $COUNT SNMP trap(s) to $HOST:$PORT using profile=$PROFILE"
echo "Run marker: $RUN_ID"

for ((i=1; i<=COUNT; i++)); do
  send_trap "$i"
  if [[ "$i" -lt "$COUNT" ]]; then
    sleep "$INTERVAL"
  fi
done

echo "Done. Query Loki with: {job=\"snmp-traps\"} |= \"${RUN_ID}\""