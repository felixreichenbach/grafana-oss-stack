"""Send random log lines to Alloy's Loki push API (loki.source.api)."""
import json
import os
import random
import time
import urllib.request

PUSH_URL = os.environ.get("PUSH_URL", "http://alloy:9999/loki/api/v1/push")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "archive")
INTERVAL = float(os.environ.get("INTERVAL_SECONDS", "2"))
BATCH = int(os.environ.get("BATCH_SIZE", "5"))

LEVELS = ["debug", "info", "info", "info", "warn", "error"]
EVENTS = [
    "archive job started",
    "archived file {n}.log ({kb} KB)",
    "checksum verified for {n}.log",
    "retention sweep removed {n} files",
    "upload to cold storage retrying (attempt {a})",
    "failed to read segment {n}: unexpected EOF",
]


def make_line():
    level = random.choice(LEVELS)
    msg = random.choice(EVENTS).format(
        n=random.randint(1, 9999), kb=random.randint(1, 4096), a=random.randint(1, 5)
    )
    return level, f"level={level} msg=\"{msg}\""


def push():
    values = []
    for _ in range(BATCH):
        level, line = make_line()
        values.append([str(time.time_ns()), line])
    body = json.dumps(
        {"streams": [{"stream": {"service_name": SERVICE_NAME}, "values": values}]}
    ).encode()
    req = urllib.request.Request(
        PUSH_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, len(values)


while True:
    try:
        status, n = push()
        print(f"pushed {n} lines -> HTTP {status}", flush=True)
    except Exception as exc:
        print(f"push failed: {exc}", flush=True)
    time.sleep(INTERVAL)
