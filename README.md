# grafana-oss-stack

A basic Docker Compose setup running Grafana OSS, Loki, and Alloy with additional features such as syslog etc.

## Services

| Service | Image | Host port |
|---------|-------|-----------|
| Grafana | grafana/grafana-oss:latest | 127.0.0.1:3001 |
| Loki | grafana/loki:latest | Internal only |
| Mimir | grafana/mimir:latest | Internal only |
| Alloy | grafana/alloy:latest | Internal only |
| PDC agent | grafana/pdc-agent:latest | None (outbound only) |
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

Only cloud mode uses `LOKI_URL` and `LOKI_USERNAME`. Authentication to Grafana Cloud uses a single access policy token, `GCLOUD_RW_API_KEY`, for all signals (logs, metrics, traces and pipelines pulled from Fleet Management). Give the token the `logs:write`, `metrics:write`, `traces:write` and `profiles:write` scopes.

Local mode in `alloy/config.local.alloy` writes directly to `http://loki:3100/loki/api/v1/push`.

`alloy/alloy-container.yml` passes through the cloud variables (`LOKI_URL`/`LOKI_USERNAME`, `MIMIR_URL`/`MIMIR_USERNAME`, `TEMPO_*`, `PYROSCOPE_*`, `OTLP_*`, `FLEET_MANAGEMENT_*` and `GCLOUD_RW_API_KEY`). `GCLOUD_RW_API_KEY` must be set: pipelines delivered by Fleet Management read it with `sys.env("GCLOUD_RW_API_KEY")`, and without it metrics writes fail with `401 invalid token`.

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

### Private Data Source Connect (PDC)

`pdc/pdc-container.yml` runs the [PDC agent](https://grafana.com/docs/grafana-cloud/connect-externally-hosted/private-data-source-connect/) so Grafana Cloud can query data sources on this Docker network, for example the local Loki.

1. In Grafana Cloud, go to **Connections > Private data source connections**, create a network and generate a token with the `pdc-signing:write` scope.
2. Set `GCLOUD_PDC_SIGNING_TOKEN`, `GCLOUD_PDC_CLUSTER` and `GCLOUD_HOSTED_GRAFANA_ID` in `.env.cloud` (see `.env.cloud.example`; the cluster and ID are shown on the network's **Configuration Details** tab).
3. Start the agent and Loki: `docker compose --env-file .env.cloud up -d pdc-agent loki`. The agent is behind the `pdc` Compose profile, so it only starts when you name it and the rest of the stack runs without PDC credentials.
4. In Grafana Cloud add a Loki data source with URL `http://loki:3100` and select the PDC network under **Private data source connect**.

The agent only makes outbound connections (SSH to `private-datasource-connect.<cluster>.grafana.net:22`), so no host port is published. Set `PDC_LOG_LEVEL=debug` to see each proxied connection. After restarting the agent, click **Save & test** on the data source again.

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

