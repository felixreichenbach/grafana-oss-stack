# grafana-oss-stack

A Docker Compose setup running Grafana OSS, Loki, Alloy, and rsyslog for syslog ingestion.

## Services

| Service | Image | Port |
|---------|-------|------|
| Grafana | grafana/grafana-oss:latest | 3000 |
| Loki | grafana/loki:latest | 3100 |
| Alloy | grafana/alloy:latest | 1514/tcp, 1514/udp |
| rsyslog relay | rsyslog/rsyslog:latest | 514/udp |

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Getting Started

### Start the stack

```sh
docker compose up -d
```

### Access Grafana

Open [http://localhost:3000](http://localhost:3000) in your browser.

Default credentials:
- **Username:** `admin`
- **Password:** `admin`

### Connect Loki as a Data Source

1. In Grafana, go to **Connections > Data Sources**.
2. Click **Add data source** and select **Loki**.
3. Set the URL to `http://loki:3100`.
4. Click **Save & test**.

## Syslog Ingestion Paths

This stack supports two ingestion paths:

- Relay path (existing): sender -> UDP 514 -> rsyslog -> TCP 1514 -> Alloy -> Loki
- Direct path (new): sender -> UDP 1514 -> Alloy -> Loki

Use the relay path if you want rsyslog in front of Alloy.
Use the direct path if you want a simpler setup with fewer moving parts.

## Querying Logs In Grafana Explore

Known-good LogQL queries:

- All syslog from this setup:

```logql
{job="meraki-syslog"}
```

- Direct UDP listener only:

```logql
{job="meraki-syslog",transport="udp"}
```

- Relay traffic (typically without the UDP transport label):

```logql
{job="meraki-syslog"} != ""
```

Tip: if logs do not appear, widen the time range in Explore first.

## Quick Local Syslog Tests

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

### Stop the stack

```sh
docker compose down
```

### Stop and remove volumes

```sh
docker compose down -v
```

## Loki

Push log entry:

```sh
curl -X POST http://localhost:3100/loki/api/v1/push \                                          
  -H "Content-Type: application/json" \
  -d '{
    "streams": [
      {
        "stream": { "job": "test", "env": "dev" },
        "values": [
          ["'"$(date +%s%N)"'", "hello from curl"]
        ]
      }
    ]
  }'
```
