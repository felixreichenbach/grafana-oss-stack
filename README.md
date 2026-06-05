# grafana-oss-stack

A basic Docker Compose setup running Grafana OSS, Loki, and Alloy with additional features such as syslog etc.

## Services

| Service | Image | Port |
|---------|-------|------|
| Grafana | grafana/grafana-oss:latest | 3000 |
| Loki | grafana/loki:latest | 3100 |
| Alloy | grafana/alloy:latest | Internal only |
| Rsyslog | rsyslog/rsyslog:latest | 514/udp |
| Telegraf | telegraf:latest | 162/udp |
| Static website (optional) | nginx:alpine | 8088 |

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

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

Open [http://localhost:3000](http://localhost:3000) in your browser.

Default credentials:
- **Username:** `admin`
- **Password:** `admin`

### Loki Data Source Provisioning

Grafana auto-registers Loki on startup via provisioning.

- Config file: `grafana/provisioning/datasources/loki.yml`
- URL used: `http://loki:3100`

To apply changes after editing provisioning files:

```sh
docker compose restart grafana
```

To verify in the UI: **Connections > Data Sources** should already contain **Loki**.

