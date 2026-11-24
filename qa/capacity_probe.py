"""Temporary, sync-worker WSGI profiler for the private capacity fixture."""
import os
import time
from pathlib import Path

from django.db import connection
from django.db.backends.base.base import BaseDatabaseWrapper as DatabaseWrapper

from garden.wsgi import application as garden

if os.environ.get("DJANGO_SETTINGS_MODULE") != "capacity_settings" or not Path(".capacity-lab").is_file():
    raise RuntimeError("Use this profiler only in the disposable capacity service.")

# Django invokes the database driver's native commit outside its cursor execute wrappers.
original_commit = DatabaseWrapper._commit
active = None


def timed_commit(db):
    begin = time.monotonic_ns()
    try:
        return original_commit(db)
    finally:
        if active is not None:
            active["commit"] += time.monotonic_ns() - begin


DatabaseWrapper._commit = timed_commit


def application(environ, start_response):
    global active
    entered = time.monotonic_ns()
    cpu = time.thread_time_ns()
    times = {"read": 0, "write": 0, "commit": 0}
    active = times

    def timed_query(execute, sql, params, many, context):
        kind = "read" if sql.lstrip().upper().startswith("SELECT") else "write"
        begin = time.monotonic_ns()
        try:
            return execute(sql, params, many, context)
        finally:
            times[kind] += time.monotonic_ns() - begin

    def headers(status, fields, exc_info=None):
        measurements = [entered, time.monotonic_ns() - entered, time.thread_time_ns() - cpu,
                        times["read"], times["write"], times["commit"]]
        fields.append(("X-Capacity-Profile", ",".join(str(v) for v in measurements)))
        return start_response(status, fields, exc_info)

    try:
        with connection.execute_wrapper(timed_query):
            return garden(environ, headers)
    finally:
        active = None
