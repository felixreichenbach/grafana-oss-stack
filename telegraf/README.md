# SNMP - Traps Ingestion

Alloy doesn't support SNMP traps natively and therefore Telegraf as intermediary is a good option to receive, preprocess and then forward events to Alloy (optional) and Loki.

## Included Telegraf Receiver

This stack now includes a `telegraf` container that:

- listens for SNMP traps on host UDP `162`
- receives them inside the container on UDP `1162`
- forwards them directly to Loki via the Loki push API

The host-to-container port mapping avoids the need for Telegraf to bind a privileged port inside the container.

## Start

```sh
docker compose up -d telegraf-snmp-traps
```

## Query In Grafana Explore

Use the Telegraf job label:

```logql
{job="snmp-traps"}
```

Telegraf sends trap tags such as source, mib, name, oid, and version as Loki labels. Trap variable bindings are included in the log line in logfmt format.

## Generate Test Traps

Send a single test trap to the local receiver:

```sh
./telegraf/snmp-trap-sim.sh
```

Send a small burst with a fixed marker:

```sh
./telegraf/snmp-trap-sim.sh --count 3 --run-id demo-snmp-traps-001
```

Send a more realistic UPS power-loss sequence:

```sh
./telegraf/snmp-trap-sim.sh --profile power-loss --run-id demo-power-loss-001
```

Send the complementary utility power restored sequence:

```sh
./telegraf/snmp-trap-sim.sh --profile power-restored --run-id demo-power-restored-001
```

Query the marker in Grafana Explore:

```logql
{job="snmp-traps"} |= "demo-snmp-traps-001"
```

The generator uses the local `snmptrap` CLI from net-snmp and sends SNMPv2c traps with `sysName.0`, `sysLocation.0`, and `sysDescr.0` varbinds.

The `power-loss` profile emits a three-stage RFC 1628 UPS-style sequence: utility power lost, low battery, and shutdown imminent. It also includes UPS runtime, battery charge, input voltage, output source, and load varbinds so the resulting logs look closer to a real UPS event stream.

The `power-restored` profile emits a two-stage recovery sequence using `upsTrapAlarmEntryRemoved`: utility power restored and low battery cleared. These events switch the output source back to normal power, set seconds on battery to zero, restore input voltage, and show the battery beginning to recover.

The Telegraf container uses the repo-local `telegraf/mibs/` directory so standard trap OIDs resolve correctly without depending on a host-level bind mount.

> [!NOTE]
> If you need to populate local MIB files, you can copy them from your host SNMP directory (e.g. Mac):
> ```sh
> cp /usr/share/snmp/mibs/*.txt telegraf/mibs/
> ```
