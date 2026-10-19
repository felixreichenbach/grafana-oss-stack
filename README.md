# grafana-oss-stack

A basic Docker Compose setup running Grafana OSS, Loki, and Alloy with additional features such as syslog etc.

## Services

| Service | Image | Host port |
|---------|-------|-----------|
| Grafana | grafana/grafana-oss:latest | 127.0.0.1:3001 |
| Loki | grafana/loki:latest | Internal only |
| Mimir | grafana/mimir:latest | Internal only |
| Alloy | grafana/alloy:latest | Internal only |
| Grafana MCP server | grafana/mcp-grafana:latest | Shared `grafana` network only |
| Tempo | grafana/tempo:latest | Shared `grafana` network only |
| Prometheus | prom/prometheus:latest | Internal only |
| Rsyslog | rsyslog/rsyslog:latest | 514/udp |
| Telegraf | telegraf:latest | 162/udp |
| Static website (optional) | nginx:alpine | 8088 |

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

Only ports that something outside the stack needs are published, and HTTP ports are bound to `127.0.0.1`. Services reach each other by service name on the compose network. Use Grafana's Explore view to query Loki, Mimir, Prometheus and Tempo.

## Getting Started

### Start the stack

```sh
docker compose --env-file .env.local up -d
```

### Switch Alloy Destination (Local vs Grafana Cloud)

Use env files to select the runtime endpoints and credentials Alloy receives:

Alloy uses `ALLOY_CONFIG_FILE` from the selected env file to choose the mounted config:

- `alloy/config.local.alloy` (local mode, no Fleet enrollment)
- `alloy/config.cloud.alloy` (cloud mode, includes Fleet `remotecfg`)

- Local Loki (default):

```sh
docker compose --env-file .env.local up -d
```

- Grafana Cloud Loki:

```sh
cp .env.cloud.example .env.cloud
# edit .env.cloud and fill in the Grafana Cloud endpoint URLs and credentials you need
docker compose --env-file .env.cloud up -d
```

Only cloud mode uses `LOKI_URL`, `LOKI_USERNAME`, and `LOKI_PASSWORD`.

Local mode in `alloy/config.local.alloy` writes directly to `http://loki:3100/loki/api/v1/push`.

`alloy/alloy-container.yml` passes through the full cloud variable set (`LOKI_*`, `MIMIR_*`, `TEMPO_*`, `PYROSCOPE_*`, `OTLP_*`, `FLEET_MANAGEMENT_*`) so they are available for future Alloy pipeline additions.

.env.cloud.example also includes Grafana Cloud endpoints for Mimir (metrics), Tempo (traces), Pyroscope (profiles), OTLP gateway, and optional Fleet Management (for Alloy remote config).

### Stop the stack

```sh
docker compose down
```

### Stop and remove volumes

```sh
docker compose down -v

# or including orphaned items
docker compose down -v --remove-orphans
```

### Access Grafana

Open [http://localhost:3001](http://localhost:3001) in your browser.

Default credentials:
- **Username:** `admin`
- **Password:** `admin`

### Connecting other projects

This stack owns a shared Docker network named `grafana` (declared in `docker-compose.yml`) and creates it on startup. Another compose project on the same Docker host joins it and reaches the services below by name. Start this stack first, because the network is `external` for everyone else:

```yaml
services:
  my-agent:
    networks: [grafana]

networks:
  grafana:
    external: true
```

| Service | URL from an attached project |
|---------|------------------------------|
| Grafana MCP server | `http://mcp-grafana:8000/mcp` |
| Tempo OTLP gRPC | `tempo:4317` |
| Tempo OTLP HTTP | `http://tempo:4318` |

All other services stay on the stack's private default network and are not reachable from attached projects. To expose another service, add `grafana` to its `networks` (keep `default` too, so it still talks to the rest of the stack):

```yaml
    networks:
      - default
      - grafana
```

Anyone on the `grafana` network can reach these services without authentication.

### Grafana MCP Server

`mcp/mcp-container.yml` runs [mcp-grafana](https://github.com/grafana/mcp-grafana) with the streamable HTTP transport at `http://mcp-grafana:8000/mcp` (shared network only). It talks to Grafana at `http://grafana:3000`.

By default it talks to the local Grafana and authenticates with the admin credentials. To use Grafana Cloud instead, set `GRAFANA_MCP_URL` and `GRAFANA_SERVICE_ACCOUNT_TOKEN` in `.env.cloud` (see `.env.cloud.example`). For anything beyond local dev, use a service account token locally too.

It is not published on the host. Other compose projects reach it over the shared network, see [Connecting other projects](#connecting-other-projects).

### Loki Data Source Provisioning

Grafana auto-registers Loki on startup via provisioning.

- Config file: `grafana/provisioning/datasources/loki.yml`
- URL used: `http://loki:3100`

### Tempo Data Source Provisioning

Grafana auto-registers Tempo on startup via provisioning.

- Config file: `grafana/provisioning/datasources/tempo.yml`
- URL used: `http://tempo:3200`

### Mimir Data Source Provisioning

Grafana auto-registers Mimir (Prometheus-compatible) on startup via provisioning.

- Config file: `grafana/provisioning/datasources/mimir.yml`
- URL used: `http://mimir:9009/prometheus`

To apply changes after editing provisioning files:

```sh
docker compose restart grafana
```

To verify in the UI: **Connections > Data Sources** should already contain **Loki**.

