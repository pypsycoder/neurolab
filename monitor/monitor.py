"""Small host-metrics collector for the private control-plane dashboard."""
import logging
import os
import shutil
import time
from pathlib import Path

import psycopg


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("neuro_lab.monitor")
DATABASE_URL = os.environ["DATABASE_URL"]
INTERVAL_SECONDS = max(30, int(os.getenv("METRICS_INTERVAL_SECONDS", "60")))


def read_temperature():
    return round(int(Path("/host/sys/thermal_temp").read_text().strip()) / 1000, 1)


def read_memory():
    values = {}
    for line in Path("/host/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip().split()[0]) * 1024
    return values["MemTotal"], values["MemAvailable"]


def sample():
    load_1m = float(Path("/host/proc/loadavg").read_text().split()[0])
    memory_total, memory_available = read_memory()
    disk = shutil.disk_usage("/srv/neuro-lab")
    return (read_temperature(), load_1m, memory_total, memory_available, disk.total, disk.free)


def ensure_schema():
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS metric_samples (
                   recorded_at TIMESTAMPTZ PRIMARY KEY DEFAULT now(),
                   temperature_c NUMERIC(4, 1) NOT NULL,
                   load_1m NUMERIC(6, 2),
                   memory_total BIGINT,
                   memory_available BIGINT,
                   disk_total BIGINT,
                   disk_free BIGINT
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS metric_samples_recorded_at_idx "
            "ON metric_samples (recorded_at DESC)"
        )
        conn.commit()


def write_sample(values):
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """INSERT INTO metric_samples
               (temperature_c, load_1m, memory_total, memory_available, disk_total, disk_free)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            values,
        )
        conn.execute("DELETE FROM metric_samples WHERE recorded_at < now() - interval '30 days'")
        conn.commit()


ensure_schema()
while True:
    try:
        values = sample()
        write_sample(values)
        log.info("temperature sample %.1fC", values[0])
    except Exception:
        log.exception("metrics collection failed")
    time.sleep(INTERVAL_SECONDS)
