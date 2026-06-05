# Rsyslog - Syslog Preprocessing

Grafana Alloy provides a Syslog receiver which expects syslog messages to meet either RFC3164 or RFC5424 (newer) standards. A lot of devices, in particular networking devices do not meet these specifications and therefore it might be necessary to use Rsyslog as a preprocesser.

## Meraki Timestamp Workaround

While Meraki devices can forward Syslog messages, they use Epoch for their timestamps which is not inline with the standard and Alloy will drop these messages.
To fix this, Rsyslog will take the message and update / reformat the Syslog header to meet the official standard.

See [`rsyslog.conf`](./rsyslog.conf) for the configuration.

Also have a look at the syslog sections in [`config.local.alloy`](../alloy/config.local.alloy) and [`config.cloud.alloy`](../alloy/config.cloud.alloy).


### Sample Meraki Syslog Messages

You can send these raw Meraki Syslog messages via command line from within one of the containers:

```shell
echo -n '<134>1 1779791764.872052699 BRBSGAWAP201_Farme_Service_ urls src=10.157.26.124:53613 dst=63.140.39.244:443 mac=C4:47:4E:37:A3:61 request: UNKNOWN https://sstats.adobe.com/...' | nc -u -w 1 syslog 514

echo -n '<134>1 1780661476.730182000 BEWILBCSW001_2_Basement_ events Port bounce requested: Ports 12 will be switched off for 5 seconds' | nc -u -w 1 syslog 514
```

### Meraki Syslog Simulator (TO BE VERIFIED)

Generate a burst of Meraki-like syslog events (flows, ids, dhcp, vpn) with one marker.
Default output format is RFC3164 (closer to common Meraki syslog style).

```sh
./scripts/meraki-syslog-sim.sh --count 20 --run-id demo-meraki-001
```

Defaults:

- Destination: `127.0.0.1:1514`
- Protocol: `udp`
- Format: `rfc3164`
- Events: `12`

For Meraki-like RFC3164 testing in this stack, prefer the relay path on UDP `514`:

```sh
./scripts/meraki-syslog-sim.sh --port 514 --proto udp --format rfc3164 --run-id demo-meraki-3164
```

Query your run marker in Explore:

```logql
{job="meraki-syslog"} |= "demo-meraki-001"
```

Use relay path instead (rsyslog on UDP 514):

```sh
./scripts/meraki-syslog-sim.sh --port 514 --proto udp --run-id demo-relay-001
```

Force RFC5424 output (for parser compatibility checks):

```sh
./scripts/meraki-syslog-sim.sh --format rfc5424 --run-id demo-rfc5424-001
```


## Quick Local Syslog Tests (TO BE VERIFIED)

Send a UDP syslog message directly to Alloy (UDP 1514):

```sh
printf '<165>1 2026-05-21T09:30:00Z host udpapp 1234 - - readme-udp-test\n' | nc -u -w 1 127.0.0.1 1514
```

Send a UDP syslog message to rsyslog relay (UDP 514):

```sh
printf '<134>May 21 09:25:00 host1 relayapp: readme-relay-test\n' | nc -u -w 1 127.0.0.1 514
```

Check with Loki HTTP API (range query):

```sh
END=$(date +%s%N)
START=$((END-600000000000))
curl -sG 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={job="meraki-syslog"}' \
  --data-urlencode "start=$START" \
  --data-urlencode "end=$END" \
  --data-urlencode 'limit=20'
```

Note: stream selectors must use `query_range`; instant `/query` is for metric queries.

## Syslog Ingestion Paths (TO BE VERIFIED)

This stack supports two ingestion paths:

- Relay path (existing): sender -> UDP 514 -> rsyslog -> TCP 1514 -> Alloy -> Loki
- Direct path (new): sender -> UDP 1514 -> Alloy -> Loki

Use the relay path if you want rsyslog in front of Alloy.
Use the direct path if you want a simpler setup with fewer moving parts.

