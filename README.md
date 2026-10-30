# grafana-oss-stack

A basic Docker Compose setup running Grafana OSS, Loki, and Alloy with additional features such as SNMP trap parsing and Grafana Cloud Fleet Management.

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
- `alloy/config.cloud.alloy` (cloud mode, bootstrap only: enrolls in Fleet Management with `remotecfg`; log and trace ingest are Fleet pipelines, see [Fleet Management pipelines](#fleet-management-pipelines))

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

### Fleet Management pipelines

In cloud mode the local Alloy config (`alloy/config.cloud.alloy`) only enrolls the collector in Fleet Management. Everything else is delivered as Fleet pipelines that live in this repo under `fleet/pipelines/`:

```
fleet/
  deploy.sh                    # validate + create/update the pipelines in Fleet
  pipelines/
    log-ingest.alloy           # Loki push API (9999) -> Grafana Cloud Loki and S3
    metrics-ingest.alloy       # Prometheus remote-write (9009) -> Grafana Cloud Mimir
    otlp-ingest.alloy          # OTLP gRPC/HTTP (4317/4318): logs, metrics, traces -> Grafana Cloud OTLP gateway
    *.json                     # per pipeline: spec name, enabled, matchers
```

The collector therefore exposes the default ingest endpoints for all three signals:

| Signal | Endpoint | Forwarded to |
|--------|----------|--------------|
| Logs | Loki push API: `POST http://<collector>:9999/loki/api/v1/push` | Grafana Cloud Loki (+ S3) |
| Metrics | Prometheus remote-write: `http://<collector>:9009/api/v1/metrics/write` | Grafana Cloud Mimir |
| Logs, metrics, traces | OTLP gRPC `:4317` / HTTP `:4318` | Grafana Cloud OTLP gateway |

Each pipeline is a plain `.alloy` file plus a small JSON spec (`name`, `enabled`, `matchers`). Collectors pick up a pipeline when their `remotecfg` attributes match its matchers (`log_ingest`, `metrics_ingest` and `otlp_ingest`, all set to `"true"` in `config.cloud.alloy`).

```sh
fleet/deploy.sh            # dry run: validates every pipeline with `alloy validate` and shows create/update
fleet/deploy.sh --apply    # creates or updates the pipelines via gcx (re-runnable, matched by spec name)
```

`deploy.sh` needs Docker and `gcx` logged in to the target stack. Collectors fetch changes on their next poll (`poll_frequency`, 1m).

Rules to keep in mind:

- Credentials and endpoints are never stored in pipelines. They are read with `sys.env(...)` from the collector's environment, so `.env.cloud` still needs `LOKI_*`, `MIMIR_*`, `OTLP_*`, `GCLOUD_RW_API_KEY`, `S3_*` and the `AWS_*` variables.
- Pipelines are isolated modules and cannot share components. Each listener port (9999, 9009, 4317, 4318) must be used by exactly one pipeline, never also by the local config.
- Rollout order when migrating an existing collector: run `fleet/deploy.sh --apply` first, then recreate the Alloy container with the new bootstrap config. Until the old listeners are gone, the pipeline's listeners cannot bind the same ports.

### S3 Log Archive

The `log-ingest` pipeline (`fleet/pipelines/log-ingest.alloy`) writes every log line received by Alloy on the Loki push API (port 9999) to an S3 bucket in addition to Grafana Cloud Loki, using `otelcol.exporter.awss3`. Objects are gzip-compressed OTLP JSON, partitioned per minute in UTC, with the stream labels kept as attributes on each log record:

```
<S3_PREFIX>/year=YYYY/month=MM/day=DD/hour=HH/minute=MM/logs_<uuid>.json.gz
```

Lines are batched (30s) into fewer objects. Only logs received on the Loki push API are written to S3; OTLP logs go to Grafana Cloud only.

1. Create a bucket and an IAM user or role with `s3:PutObject` on `arn:aws:s3:::<S3_BUCKET>/<S3_PREFIX>/*`.
2. Set `S3_BUCKET`, `S3_REGION`, `S3_PREFIX` and the `AWS_*` credentials in `.env.cloud` (see `.env.cloud.example`).
3. Deploy the pipeline (`fleet/deploy.sh --apply`) and recreate Alloy: `docker compose --env-file .env.cloud up -d --force-recreate alloy`.

`S3_BUCKET` and `S3_REGION` must be set on the collector; the pipeline fails to start otherwise. Local mode (`config.local.alloy`) does not write to S3.

### Private Data Source Connect (PDC)

`pdc/pdc-container.yml` runs the [PDC agent](https://grafana.com/docs/grafana-cloud/connect-externally-hosted/private-data-source-connect/) so Grafana Cloud can query data sources on this Docker network, for example the local Loki.

1. In Grafana Cloud, go to **Connections > Private data source connections**, create a network and generate a token with the `pdc-signing:write` scope.
2. Set `GCLOUD_PDC_SIGNING_TOKEN`, `GCLOUD_PDC_CLUSTER` and `GCLOUD_HOSTED_GRAFANA_ID` in `.env.cloud` (see `.env.cloud.example`; the cluster and ID are shown on the network's **Configuration Details** tab).
3. Start the agent and Loki: `docker compose --env-file .env.cloud up -d pdc-agent loki`.
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

