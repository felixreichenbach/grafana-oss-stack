"""Simulate a realistic archiving service and send its logs to Alloy.

The simulated service runs archive jobs: it scans a directory, uploads files to object storage (with
multipart uploads, throttling, retries and the occasional failure), verifies checksums and reports a job
summary. Between jobs it logs health checks. Records of one job share a trace id and every file upload has
its own span id. Severities, durations and sizes follow realistic distributions (mostly INFO, some DEBUG,
few WARN, rare ERROR).

Every tick sends one batch of records to each target in TARGETS (comma separated):

  loki  Loki push API (loki.source.api). One log line per record in LOKI_LINE_FORMAT:
          logfmt (default)  ts=... level=info component=uploader msg="..." key=value ... trace_id=...
          json              OpenTelemetry Logs Data Model JSON (Timestamp, SeverityText, Body, Resource, ...)
          plain             just the message
        Stream labels follow Loki's OTLP naming (service_name, level, ...).
  otlp  OTLP/HTTP JSON (otelcol.receiver.otlp, path /v1/logs): message as body, details as attributes.

Set ONCE=true to send a single batch and exit.
"""
import json
import math
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

LOKI_PUSH_URL = os.environ.get("LOKI_PUSH_URL", os.environ.get("PUSH_URL", "http://alloy:3100/loki/api/v1/push"))
OTLP_LOGS_URL = os.environ.get("OTLP_LOGS_URL", "http://alloy:4318/v1/logs")
TARGETS = [t.strip() for t in os.environ.get("TARGETS", "loki,otlp").split(",") if t.strip()]
LOKI_LINE_FORMAT = os.environ.get("LOKI_LINE_FORMAT", "logfmt").lower()
INTERVAL = float(os.environ.get("INTERVAL_SECONDS", "2"))
BATCH = int(os.environ.get("BATCH_SIZE", "5"))
ONCE = os.environ.get("ONCE", "false").lower() == "true"

SERVICE_NAME = os.environ.get("SERVICE_NAME", "archive")
SERVICE_VERSION = os.environ.get("SERVICE_VERSION", "1.0.0")
ENVIRONMENT = os.environ.get("DEPLOYMENT_ENVIRONMENT", "docker")
INSTANCE_ID = os.environ.get("SERVICE_INSTANCE_ID", str(uuid.uuid4()))
HOST_NAME = socket.gethostname()
SCOPE_NAME = "loggen"
BUCKET = os.environ.get("ARCHIVE_BUCKET", "corp-archive-prod")

# OpenTelemetry severity text -> SeverityNumber (first number of each range, see the Logs Data Model).
SEVERITIES = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}

RESOURCE = {
    "service.name": SERVICE_NAME,
    "service.version": SERVICE_VERSION,
    "service.instance.id": INSTANCE_ID,
    "deployment.environment.name": ENVIRONMENT,
    "host.name": HOST_NAME,
}

STORAGE_ERRORS = [
    ("RequestTimeout", "Your socket connection to the server was not read from or written to within the timeout period"),
    ("SlowDown", "Please reduce your request rate"),
    ("InternalError", "We encountered an internal error. Please try again"),
    ("ConnectionResetError", "[Errno 104] Connection reset by peer"),
]
STACKTRACE = (
    "Traceback (most recent call last):\n"
    '  File "/app/archive/uploader.py", line 142, in upload_object\n'
    "    self._client.put_object(Bucket=self._bucket, Key=key, Body=body)\n"
    '  File "/usr/local/lib/python3.12/site-packages/botocore/client.py", line 569, in _api_call\n'
    "    return self._make_api_call(operation_name, kwargs)\n"
    "botocore.exceptions.ClientError: {error}"
)


def field(logfmt_key, otel_key, value):
    """One structured field: short key for logfmt, dotted semantic-convention style key for OTLP."""
    return (logfmt_key, otel_key, value)


def ev(severity, component, msg, fields=(), trace_id=None, span_id=None, extra_attrs=None):
    return {
        "severity": severity,
        "component": component,
        "msg": msg,
        "fields": list(fields),
        "trace_id": trace_id,
        "span_id": span_id,
        "extra_attrs": extra_attrs or {},
    }


def human_size(n):
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(n // 1024, 1)} KB"


def simulate():
    """Endless generator of events in the order a real service would log them."""
    while True:
        job_id = f"job-{random.randint(10000, 99999)}"
        trace_id = secrets.token_hex(16)
        root_span = secrets.token_hex(8)
        day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        source = f"/data/exports/{day.replace('/', '-')}"
        files = random.randint(3, 9)
        jf = field("job_id", "archive.job.id", job_id)

        yield ev("INFO", "scheduler", f"archive job started job_id={job_id} files={files}",
                 [jf, field("files", "archive.job.files", files)], trace_id, root_span)
        yield ev("DEBUG", "scanner", f"scanned source directory {source}, {files} files eligible",
                 [jf, field("path", "file.directory", source), field("entries", "archive.scan.entries", files + random.randint(0, 40))],
                 trace_id, root_span)

        uploaded = failed = total_bytes = 0
        job_started = time.monotonic()
        for _ in range(files):
            span = secrets.token_hex(8)
            name = f"export-{random.randint(1000, 9999)}.csv.gz"
            key = f"archive/{day}/{name}"
            size = int(min(random.lognormvariate(math.log(2_000_000), 1.4), 900_000_000))
            kf = [jf, field("key", "archive.object.key", key), field("bytes", "archive.object.size", size)]

            yield ev("INFO", "uploader", f"uploading {name} ({human_size(size)}) to s3://{BUCKET}/{key}", kf, trace_id, span)
            if size > 8 * 1024 * 1024:
                parts = min(size // (8 * 1024 * 1024) + 1, 6)
                for part in range(1, parts + 1):
                    yield ev("DEBUG", "uploader", f"multipart part {part}/{parts} uploaded etag={secrets.token_hex(8)}",
                             kf + [field("part", "archive.upload.part", part)], trace_id, span)

            attempt = 1
            roll = random.random()
            retries = 0 if roll < 0.86 else (1 if roll < 0.93 else (2 if roll < 0.97 else 3))
            while attempt <= retries:
                code, text = random.choice(STORAGE_ERRORS)
                backoff = 200 * 2 ** (attempt - 1) + random.randint(0, 100)
                yield ev("WARN", "uploader", f"upload attempt {attempt} failed, retrying in {backoff}ms: {code}",
                         kf + [field("attempt", "archive.upload.attempt", attempt), field("backoff_ms", "archive.retry.backoff_ms", backoff),
                               field("error", "exception.message", f"{code}: {text}")],
                         trace_id, span, {"exception.type": code})
                attempt += 1

            if retries == 3:
                code, text = random.choice(STORAGE_ERRORS)
                error = f"{code}: {text}"
                yield ev("ERROR", "uploader", f"giving up on {name} after {attempt} attempts: {code}",
                         kf + [field("attempt", "archive.upload.attempt", attempt), field("error", "exception.message", error)],
                         trace_id, span, {"exception.type": code, "exception.stacktrace": STACKTRACE.format(error=error)})
                failed += 1
                continue

            duration = int(size / random.uniform(8e6, 40e6) * 1000) + random.randint(20, 120)
            yield ev("INFO", "uploader", f"uploaded {name} in {duration}ms", kf + [field("duration_ms", "archive.upload.duration_ms", duration)],
                     trace_id, span)

            if random.random() < 0.02:
                expected, actual = secrets.token_hex(16), secrets.token_hex(16)
                yield ev("ERROR", "verifier", f"checksum mismatch for {name}: expected {expected[:8]}..., got {actual[:8]}...",
                         kf + [field("expected", "archive.checksum.expected", expected), field("actual", "archive.checksum.actual", actual)],
                         trace_id, span, {"exception.type": "ChecksumMismatch"})
                failed += 1
                continue
            yield ev("DEBUG", "verifier", f"checksum verified for {name}", kf + [field("md5", "archive.checksum.md5", secrets.token_hex(16))],
                     trace_id, span)
            uploaded += 1
            total_bytes += size

            # Health checks and other background noise between the work.
            for _ in range(random.choice([0, 0, 0, 0, 1])):
                yield health_check()

        elapsed = round(time.monotonic() - job_started + random.uniform(2, 40), 1)
        severity = "WARN" if failed else "INFO"
        yield ev(severity, "scheduler", f"archive job finished job_id={job_id} uploaded={uploaded} failed={failed} bytes={total_bytes}",
                 [jf, field("uploaded", "archive.job.uploaded", uploaded), field("failed", "archive.job.failed", failed),
                  field("bytes", "archive.job.bytes", total_bytes), field("duration_s", "archive.job.duration_s", elapsed)],
                 trace_id, root_span)
        if random.random() < 0.3:
            removed = random.randint(0, 25)
            yield ev("INFO", "retention", f"retention sweep removed {removed} expired objects",
                     [field("removed", "archive.retention.removed", removed), field("retention_days", "archive.retention.days", 90)])
        for _ in range(random.randint(1, 3)):
            yield health_check()


def health_check():
    latency = round(random.uniform(0.3, 2.5), 1)
    return ev("INFO", "http", f"GET /healthz 200 {latency}ms",
              [field("method", "http.request.method", "GET"), field("path", "url.path", "/healthz"),
               field("status", "http.response.status_code", 200), field("duration_ms", "http.server.request.duration_ms", latency)])


SIMULATION = simulate()


def make_records(count):
    """Take the next `count` events and timestamp them, with random gaps, ending at about now."""
    now = time.time_ns()
    mean_gap = INTERVAL * 1e9 / max(count, 1)
    gaps = [int(random.expovariate(1 / mean_gap)) for _ in range(count)]
    scale = min(1.0, INTERVAL * 1e9 / max(sum(gaps), 1))  # keep the whole batch inside the interval
    gaps = [int(g * scale) for g in gaps]
    stamps, t = [], now
    for g in reversed(gaps):
        stamps.append(t)
        t -= g
    stamps.reverse()
    records = []
    for stamp in stamps:
        e = next(SIMULATION)
        attrs = {"component": e["component"]}
        attrs.update({otel_key: value for _, otel_key, value in e["fields"]})
        attrs.update(e["extra_attrs"])
        records.append(
            {
                "time_ns": stamp,
                "observed_ns": stamp + random.randint(1_000_000, 40_000_000),
                "severity_text": e["severity"],
                "severity_number": SEVERITIES[e["severity"]],
                "component": e["component"],
                "body": e["msg"],
                "fields": e["fields"],
                "attributes": attrs,
                "trace_id": e["trace_id"],
                "span_id": e["span_id"],
                "trace_flags": 1 if e["trace_id"] else 0,
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
    """ExportLogsServiceRequest in OTLP/JSON (trace and span ids are hex strings; omitted when there is no trace)."""
    log_records = []
    for r in records:
        rec = {
            "timeUnixNano": str(r["time_ns"]),
            "observedTimeUnixNano": str(r["observed_ns"]),
            "severityNumber": r["severity_number"],
            "severityText": r["severity_text"],
            "body": {"stringValue": r["body"]},
            "attributes": key_values(r["attributes"]),
            "flags": r["trace_flags"],
        }
        if r["trace_id"]:
            rec["traceId"] = r["trace_id"]
            rec["spanId"] = r["span_id"]
        log_records.append(rec)
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": key_values(RESOURCE)},
                "scopeLogs": [{"scope": {"name": SCOPE_NAME, "version": SERVICE_VERSION}, "logRecords": log_records}],
            }
        ]
    }


def rfc3339(ns, digits=3):
    micro = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
    return micro[: len(micro) - (6 - digits)] + "Z"


def logfmt_value(value):
    text = str(value)
    if text == "" or any(c in text for c in ' ="\\\n\t'):
        return json.dumps(text)
    return text


def logfmt_line(r):
    parts = [f"ts={rfc3339(r['time_ns'])}", f"level={r['severity_text'].lower()}", f"component={r['component']}",
             f"msg={logfmt_value(r['body'])}"]
    parts += [f"{k}={logfmt_value(v)}" for k, _, v in r["fields"]]
    if r["trace_id"]:
        parts += [f"trace_id={r['trace_id']}", f"span_id={r['span_id']}"]
    return " ".join(parts)


def json_line(r):
    """The record following the OpenTelemetry Logs Data Model."""
    doc = {
        "Timestamp": rfc3339(r["time_ns"], 6),
        "ObservedTimestamp": rfc3339(r["observed_ns"], 6),
        "SeverityText": r["severity_text"],
        "SeverityNumber": r["severity_number"],
        "Body": r["body"],
        "Resource": RESOURCE,
        "InstrumentationScope": {"Name": SCOPE_NAME, "Version": SERVICE_VERSION},
        "Attributes": r["attributes"],
    }
    if r["trace_id"]:
        doc.update({"TraceId": r["trace_id"], "SpanId": r["span_id"], "TraceFlags": r["trace_flags"]})
    return json.dumps(doc, separators=(",", ":"))


LINE_FORMATTERS = {"logfmt": logfmt_line, "json": json_line, "plain": lambda r: r["body"]}


def build_loki(records):
    """Loki push request: one stream per severity (the level label), one line per record."""
    line_of = LINE_FORMATTERS[LOKI_LINE_FORMAT]
    streams = {}
    for r in records:
        level = r["severity_text"].lower()
        labels = {
            "service_name": SERVICE_NAME,
            "service_instance_id": INSTANCE_ID,
            "deployment_environment_name": ENVIRONMENT,
            "level": level,
        }
        streams.setdefault(level, {"stream": labels, "values": []})["values"].append([str(r["time_ns"]), line_of(r)])
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
    if LOKI_LINE_FORMAT not in LINE_FORMATTERS:
        sys.exit(f"unknown LOKI_LINE_FORMAT {LOKI_LINE_FORMAT!r}; use one of {sorted(LINE_FORMATTERS)}")
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    print(f"loggen service={SERVICE_NAME} targets={TARGETS} line_format={LOKI_LINE_FORMAT} batch={BATCH} interval={INTERVAL}s", flush=True)
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
