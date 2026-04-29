# grafana-oss-stack

A basic Docker Compose setup running Grafana OSS, Loki, and Alloy.

## Services

| Service | Image | Port |
|---------|-------|------|
| Grafana | grafana/grafana-oss:latest | 3000 |
| Loki | grafana/loki:latest | 3100 |
| Alloy | grafana/alloy:latest | 12345 |

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

## Alloy

Alloy is included as a blank starter and loads its configuration from `./config.alloy`.

The default config only sets Alloy logging, so you can add your own pipelines and destinations.

Open [http://localhost:12345](http://localhost:12345) to access the Alloy UI.

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
