"""Generate OpenTelemetry-style log records and send them to Alloy.

Every tick produces one batch of records that is sent to each target in TARGETS (comma separated):

  loki  Loki push API (loki.source.api). One JSON log line per record following the OpenTelemetry Logs
        Data Model (Timestamp, SeverityText, SeverityNumber, Body, TraceId, SpanId, Resource, ...),
        with low-cardinality stream labels named like Loki's own OTLP mapping (service_name, level, ...).
  otlp  OTLP/HTTP JSON (otelcol.receiver.otlp, path /v1/logs) as ExportLogsServiceRequest.

Set ONCE=true to send a single batch and exit.
"""
import json
import os
import random
import secrets
import signal
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

LOKI_PUSH_URL = os.environ.get("LOKI_PUSH_URL", os.environ.get("PUSH_URL", "http://alloy:9999/loki/api/v1/push"))
OTLP_LOGS_URL = os.environ.get("OTLP_LOGS_URL", "http://alloy:4318/v1/logs")
TARGETS = [t.strip() for t in os.environ.get("TARGETS", "loki,otlp").split(",") if t.strip()]
INTERVAL = float(os.environ.get("INTERVAL_SECONDS", "2"))
BATCH = int(os.environ.get("BATCH_SIZE", "5"))
ONCE = os.environ.get("ONCE", "false").lower() == "true"

SERVICE_NAME = os.environ.get("SERVICE_NAME", "archive")
SERVICE_VERSION = os.environ.get("SERVICE_VERSION", "1.0.0")
ENVIRONMENT = os.environ.get("DEPLOYMENT_ENVIRONMENT", "docker")
INSTANCE_ID = os.environ.get("SERVICE_INSTANCE_ID", str(uuid.uuid4()))
HOST_NAME = socket.gethostname()
SCOPE_NAME = "loggen"

# OpenTelemetry severity text -> SeverityNumber (first number of each range, see the Logs Data Model).
SEVERITIES = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}
SEVERITY_WEIGHTS = ["DEBUG", "INFO", "INFO", "INFO", "WARN", "ERROR"]

RESOURCE = {
    "service.name": SERVICE_NAME,
    "service.version": SERVICE_VERSION,
    "service.instance.id": INSTANCE_ID,
    "deployment.environment.name": ENVIRONMENT,
    "host.name": HOST_NAME,
}


def event(severity):
    """Return (body, attributes) for one record of the given severity."""
    n = random.randint(1, 9999)
    if severity == "ERROR":
        return f"failed to read segment {n}: unexpected EOF", {
            "archive.segment.id": n,
            "exception.type": "EOFError",
            "exception.message": "unexpected EOF",
        }
    if severity == "WARN":
        attempt = random.randint(1, 5)
        return f"upload to cold storage retrying (attempt {attempt})", {
            "archive.retry.attempt": attempt,
            "archive.storage.tier": "cold",
        }
    if severity == "DEBUG":
        return f"checksum verified for {n}.log", {"archive.file.name": f"{n}.log", "archive.checksum.valid": True}
    kb = random.randint(1, 4096)
    return random.choice(
        [
            f"archived file {n}.log ({kb} KB)",
            f"retention sweep removed {n} files",
            "archive job started",
        ]
    ), {"archive.file.name": f"{n}.log", "archive.file.size": kb * 1024}


def make_records(count):
    """Build `count` log records of one simulated archive job (shared trace id), spread over the last INTERVAL."""
    now = time.time_ns()
    observed = now
    trace_id = secrets.token_hex(16)
    gap = int(INTERVAL * 1e9 / max(count, 1))
    records = []
    for i in range(count):
        severity = random.choice(SEVERITY_WEIGHTS)
        body, attrs = event(severity)
        records.append(
            {
                "time_ns": now - (count - i) * gap,
                "observed_ns": observed,
                "severity_text": severity,
                "severity_number": SEVERITIES[severity],
                "body": body,
                "attributes": attrs,
                "trace_id": trace_id,
                "span_id": secrets.token_hex(8),
                "trace_flags": 1,
            }
        )
    return records


def any_value(value):
    """OTLP JSON AnyValue (int64 values are strings, as in the protobuf JSON mapping)."""
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def key_values(mapping):
    return [{"key": k, "value": any_value(v)} for k, v in mapping.items()]


def build_otlp(records):
    """ExportLogsServiceRequest in OTLP/JSON (trace and span ids are hex strings)."""
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": key_values(RESOURCE)},
                "scopeLogs": [
                    {
                        "scope": {"name": SCOPE_NAME, "version": SERVICE_VERSION},
                        "logRecords": [
                            {
                                "timeUnixNano": str(r["time_ns"]),
                                "observedTimeUnixNano": str(r["observed_ns"]),
                                "severityNumber": r["severity_number"],
                                "severityText": r["severity_text"],
                                "body": {"stringValue": r["body"]},
                                "attributes": key_values(r["attributes"]),
                                "flags": r["trace_flags"],
                                "traceId": r["trace_id"],
                                "spanId": r["span_id"],
                            }
                            for r in records
                        ],
                    }
                ],
            }
        ]
    }


def rfc3339(ns):
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def build_loki(records):
    """Loki push request: one stream per severity, each line a JSON object following the OTel Logs Data Model."""
    streams = {}
    for r in records:
        level = r["severity_text"].lower()
        line = json.dumps(
            {
                "Timestamp": rfc3339(r["time_ns"]),
                "ObservedTimestamp": rfc3339(r["observed_ns"]),
                "TraceId": r["trace_id"],
                "SpanId": r["span_id"],
                "TraceFlags": r["trace_flags"],
                "SeverityText": r["severity_text"],
                "SeverityNumber": r["severity_number"],
                "Body": r["body"],
                "Resource": RESOURCE,
                "InstrumentationScope": {"Name": SCOPE_NAME, "Version": SERVICE_VERSION},
                "Attributes": r["attributes"],
            },
            separators=(",", ":"),
        )
        labels = {
            "service_name": SERVICE_NAME,
            "service_instance_id": INSTANCE_ID,
            "deployment_environment_name": ENVIRONMENT,
            "level": level,
        }
        streams.setdefault(level, {"stream": labels, "values": []})["values"].append([str(r["time_ns"]), line])
    return {"streams": list(streams.values())}


def post(url, payload, retries=3):
    data = json.dumps(payload).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            # 4xx means the payload is wrong; retrying will not help.
            detail = exc.read()[:300].decode(errors="replace")
            last = f"HTTP {exc.code}: {detail}"
            if exc.code < 500:
                break
        except Exception as exc:  # connection refused while Alloy starts, timeouts, ...
            last = str(exc)
        time.sleep(min(2**attempt, 8))
    raise RuntimeError(last)


SENDERS = {
    "loki": (LOKI_PUSH_URL, build_loki),
    "otlp": (OTLP_LOGS_URL, build_otlp),
}

stop = False


def handle_signal(signum, _frame):
    global stop
    stop = True


def main():
    unknown = [t for t in TARGETS if t not in SENDERS]
    if unknown:
        sys.exit(f"unknown TARGETS {unknown}; use loki and/or otlp")
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    print(f"loggen service={SERVICE_NAME} targets={TARGETS} batch={BATCH} interval={INTERVAL}s", flush=True)
    while not stop:
        records = make_records(BATCH)
        for target in TARGETS:
            url, build = SENDERS[target]
            try:
                status = post(url, build(records))
                print(f"{target}: sent {len(records)} records -> HTTP {status}", flush=True)
            except Exception as exc:
                print(f"{target}: send failed: {exc}", flush=True)
        if ONCE:
            break
        deadline = time.monotonic() + INTERVAL
        while not stop and time.monotonic() < deadline:
            time.sleep(0.2)


if __name__ == "__main__":
    main()
