# grafana-oss-stack

A basic Docker Compose setup running Grafana OSS and Loki.

## Services

| Service | Image | Port |
|---------|-------|------|
| Grafana | grafana/grafana-oss:latest | 3000 |
| Loki | grafana/loki:latest | 3100 |

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
