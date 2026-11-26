"""Run one closed-loop Little Garden capacity trial on Linux. No remote target."""
import argparse
import asyncio
import collections
import heapq
import http.cookies
import itertools
import json
import math
import os
from pathlib import Path
import random
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode

REPO = Path(__file__).resolve().parents[1]
CLOCK = time.monotonic
# 100% utilization consumes two CPU-seconds per second of wall time.
USEC_PER_CPU_PERCENT = 2 * 1_000_000 / 100


def application_cpus():
    physical = []
    available = os.sched_getaffinity(0)
    generator = set(available)
    for cpu in sorted(generator):
        if cpu not in generator:
            continue
        physical.append(cpu)
        topology = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        siblings = (topology / "thread_siblings_list").read_text().strip().split(",")
        for group in siblings:
            bounds = list(map(int, group.split("-")))
            generator.difference_update(range(bounds[0], bounds[-1] + 1))
        if len(physical) == 2:
            break
    if len(available) < 2:
        raise RuntimeError("Two logical CPUs are needed for this trial.")
    if len(physical) < 2:
        # Some VMs expose both vCPUs as threads of a single physical core.
        return sorted(available)[:2], set()
    return physical, generator


class AdmissionQueue:
    """Model a front end admitting at most one request per available app worker."""
    def __init__(self, workers, policy):
        self.available = workers
        self.policy = policy
        self.sequence = itertools.count()
        self.waiters = []

    async def acquire(self, kind):
        if self.available:
            self.available -= 1
            return
        ticket = asyncio.get_running_loop().create_future()
        priority = 0 if self.policy == "answers-first" and kind == "answer" else 1
        heapq.heappush(self.waiters, (priority, next(self.sequence), ticket))
        try:
            await ticket
        except asyncio.CancelledError:
            if not ticket.cancelled():
                self.release()
            raise

    def release(self):
        while self.waiters:
            _, _, ticket = heapq.heappop(self.waiters)
            if not ticket.done():
                ticket.set_result(None)
                return
        self.available += 1


class TrialRetired(Exception):
    """The synthetic household stopped issuing new requests at the load step."""


class Trial:
    def __init__(self, lab, seconds, ramp, settle, idle_poll, admission, step_down_to):
        self.socket = lab / "app.sock"
        self.admission = admission
        self.ramp = ramp
        self.idle_poll = idle_poll
        self.start = CLOCK() + ramp + settle
        self.answer_windows = [[], [], []]
        self.exhausted = 0
        self.end = self.start + seconds
        self.step_down_to = step_down_to
        self.cutover = self.start + seconds / 3
        self.retiring_sessions = set()
        self.pending = {}
        self.drain_seconds = 0
        self.recovery_samples = []
        self.recovery_answers = collections.defaultdict(list)
        self.latencies = collections.defaultdict(list)
        self.profiles = collections.defaultdict(lambda: collections.defaultdict(list))
        self.errors = collections.Counter()
        self.confirmed = 0
        self.completed = 0
        self.mirror_frames = 0
        self.reused_frames = 0
        self.mirror_bytes = 0
        self.direct_users_served = set()
        self.viewer_errors = collections.Counter()
        self.expired_frames = 0
        self.responded = set()

    async def http(self, cookies, path, kind, fields=None, *, previous_step=False):
        began = CLOCK()
        if self.step_down_to is not None:
            if began >= self.cutover and cookies["sessionid"] in self.retiring_sessions:
                raise TrialRetired()
            self.pending[asyncio.current_task()] = began
        writer = None
        admitted = False
        try:
            async with asyncio.timeout(10):
                if self.admission:
                    await self.admission.acquire(kind)
                    admitted = True
                reader, writer = await asyncio.open_unix_connection(self.socket)
                method = "GET" if fields is None else "POST"
                body = urlencode(fields or {}).encode()
                headers = [f"{method} {path} HTTP/1.0", "Host: localhost", "Accept: application/json",
                           "Cookie: " + "; ".join(f"{k}={v}" for k, v in cookies.items()),
                           "X-CSRFToken: " + cookies["csrftoken"], "Content-Type: application/x-www-form-urlencoded",
                           f"Content-Length: {len(body)}"]
                writer.write(("\r\n".join(headers) + "\r\n\r\n").encode() + body)
                await writer.drain()
                raw = await reader.read()
            head, content = raw.split(b"\r\n\r\n", 1)
            code = int(head.split(b" ", 2)[1])
            if code == 404 and previous_step:
                # The server only retains the previous question briefly during its celebration.
                # The browser keeps playing and broadcasts again on the next screen.
                self.expired_frames += 1
                return None
            if code != 200:
                raise ValueError(f"HTTP {code}")
            for line in head.split(b"\r\n"):
                if self.start <= began < self.end and line.startswith(b"X-Capacity-Profile:"):
                    entered, wall, cpu, reads, writes, commit = map(int, line.split(b":", 1)[1].split(b","))
                    components = {"before_wsgi": (entered / 1e9 - began) * 1e3, "django": wall / 1e6,
                                  "after_wsgi": (CLOCK() - (entered + wall) / 1e9) * 1e3,
                                  "worker_cpu": cpu / 1e6, "sql_reads": reads / 1e6,
                                  "sql_writes": writes / 1e6, "commits": commit / 1e6}
                    for label, value in components.items():
                        self.profiles[kind][label].append(value)
                if line.lower().startswith(b"set-cookie:"):
                    jar = http.cookies.SimpleCookie(line[11:].decode())
                    cookies.update({name: morsel.value for name, morsel in jar.items()})
            return content
        except (OSError, ValueError, TimeoutError) as error:
            self.errors[f"{kind}: {error}"] += 1
            raise
        finally:
            if admitted:
                self.admission.release()
            if writer:
                writer.close()
            if self.step_down_to is not None:
                finished = CLOCK()
                del self.pending[asyncio.current_task()]
                if began < self.cutover <= finished:
                    self.drain_seconds = max(self.drain_seconds, finished - self.cutover)
                if kind == "answer" and self.start <= began < self.end:
                    second = math.floor(began - self.cutover)
                    self.recovery_answers[second].append((finished - began) * 1000)
            if self.start <= began < self.end:
                duration = 1000 * (CLOCK() - began)
                self.latencies[kind].append(duration)
                if kind == "answer":
                    third = int(3 * (began - self.start) / (self.end - self.start))
                    self.answer_windows[third].append(duration)

    async def child(self, family, watched, direct):
        child, session, parent, assignments = family
        rng = random.Random(child)
        cookies = {"sessionid": session, "csrftoken": secrets.token_hex(16)}
        adult = {"sessionid": parent, "csrftoken": secrets.token_hex(16)}

        source = secrets.token_hex(16) if direct else ""
        peer_id = secrets.token_hex(16) if direct else ""
        relay_requested = True

        async def poll_parent():
            seen = scene = known_source = ""
            while CLOCK() < self.end:
                began = CLOCK()
                signal = {"seen": seen, "scene": scene}
                if direct and known_source:
                    signal.update(id=peer_id, source=known_source, direct=True)
                raw = await self.http(adult, "/co-view/watch/", "mirror",
                                      {"child": child, "signals": json.dumps({str(child): signal})})
                if self.start <= began < self.end:
                    self.mirror_bytes += len(raw)
                reply = json.loads(raw)
                frame = reply["children"][str(child)]
                if frame:
                    scene = frame["scene"]
                    known_source = frame.get("source", "")
                    if frame.get("success"):
                        seen = frame["success"]["scene"]
                    if self.start <= began < self.end:
                        self.mirror_frames += 1
                        if frame.get("reuse"):
                            self.reused_frames += 1
                            self.direct_users_served.add(child)
                await asyncio.sleep(.9)

        async def think(row, step, delay, *, previous_step=False):
            nonlocal relay_requested
            until = CLOCK() + delay
            while CLOCK() < min(until, self.end):
                data = {"screen": "lesson", "assignment": row, "step": step}
                if direct:
                    data.update(source=source, peers=peer_id)
                    if not relay_requested:
                        data["metadata"] = "1"
                response = await self.http(cookies, f"/co-view/share/{child}/", "presence", data,
                                           previous_step=previous_step)
                state = json.loads(response) if response else {}
                active_viewer = state.get("watching", watched)
                relay_requested = state.get("relay", True)
                await asyncio.sleep(max(0, min(.65 if active_viewer else self.idle_poll, until - CLOCK())))

        await asyncio.sleep(rng.uniform(0, self.ramp))
        viewer = asyncio.create_task(poll_parent()) if watched else None
        try:
            await self.http(cookies, "/", "garden")
            for row, answers in assignments:
                path = f"/play/{row}/"
                for step, answer in enumerate(answers):
                    if CLOCK() >= self.end:
                        return
                    page = await self.http(cookies, path, "question")
                    token = re.search(rb'name="submission" value="([0-9a-f-]+)"', page)
                    if not token or f'name="step" value="{step}"'.encode() not in page:
                        raise ValueError("Unexpected question")
                    fields = {"step": step, "submission": token[1].decode(), "active_ms": "6000"}
                    await think(row, step, rng.uniform(5, 8))
                    if CLOCK() >= self.end:
                        return
                    if rng.random() < .10:
                        retry = json.loads(await self.http(cookies, path, "answer", {**fields, "answer": "?"}))
                        if retry.get("result") != "retry":
                            raise ValueError("Unexpected retry")
                        self.confirmed += 1
                        fields["submission"] = retry["submission"]
                        await think(row, step, 2)
                        if CLOCK() >= self.end:
                            return
                    began = CLOCK()
                    reply = json.loads(await self.http(cookies, path, "answer", {**fields, "answer": answer}))
                    if reply.get("result") != "correct":
                        raise ValueError("Unexpected answer result")
                    self.confirmed += 1
                    if self.start <= began < self.end:
                        self.responded.add(child)
                        self.completed += int(reply["next"] == "/")
                    await think(row, step, 2, previous_step=True)
                if CLOCK() < self.end:
                    await self.http(cookies, "/", "garden")
            if CLOCK() < self.end:
                self.exhausted += 1
        except TrialRetired:
            return
        finally:
            if viewer:
                viewer.cancel()
                outcome, = await asyncio.gather(viewer, return_exceptions=True)
                if isinstance(outcome, Exception) and not isinstance(outcome, TrialRetired):
                    self.viewer_errors[str(outcome)] += 1

    async def run(self, families, watched, direct_percent, group):
        def cpu():
            stat = dict(line.split() for line in (group / "cpu.stat").read_text().splitlines())
            return int(stat["usage_usec"])

        if self.step_down_to is not None:
            for _, child_session, parent_session, _ in families[self.step_down_to:]:
                self.retiring_sessions.update((child_session, parent_session))
        tasks = []
        watchers = 0
        for i, family in enumerate(families):
            # Spread the selected viewers across the cohort, including smaller stages.
            has_viewer = (i + 1) * watched // 100 > i * watched // 100
            direct = has_viewer and (watchers + 1) * direct_percent // 100 > watchers * direct_percent // 100
            watchers += int(has_viewer)
            tasks.append(asyncio.create_task(self.child(family, has_viewer, direct)))
        await asyncio.sleep(max(0, self.start - CLOCK()))
        def pressure():
            totals = {}
            for name in ("cpu", "io", "memory"):
                for line in (group / f"{name}.pressure").read_text().splitlines():
                    mode, *fields = line.split()
                    totals[f"{name}_{mode}"] = int(dict(field.split("=") for field in fields)["total"])
            return totals

        initial_pressure = pressure()
        begin, cpu0, memory = CLOCK(), cpu(), 0
        monitor_lag = 0
        cpu_samples = []
        last_time, last_cpu = begin, cpu0
        resource_windows = []
        window_length = (self.end - self.start) / 3
        for third in range(3):
            until = self.start + (third + 1) * window_length
            window_start, window_cpu = last_time, last_cpu
            peak_bytes = 0
            while last_time < until:
                tick = CLOCK()
                interval = min(1, max(0, until - tick))
                await asyncio.sleep(interval)
                now, used = CLOCK(), cpu()
                monitor_lag = max(monitor_lag, now - tick - interval)
                if now - last_time > .1:
                    cpu_samples.append((used - last_cpu) / (now - last_time) / USEC_PER_CPU_PERCENT)
                if self.step_down_to is not None and now - last_time > .1:
                    self.recovery_samples.append({
                        "end_seconds_from_drop": round(now - self.cutover, 2),
                        "cpu_pct_of_2": round((used - last_cpu) / (now - last_time) / USEC_PER_CPU_PERCENT, 1),
                        "requests_in_flight": len(self.pending),
                        "pre_drop_requests_in_flight": sum(t < self.cutover for t in self.pending.values()),
                    })
                last_time, last_cpu = now, used
                peak_bytes = max(peak_bytes, int((group / "memory.current").read_text()))
            memory = max(memory, peak_bytes)
            duration = last_time - window_start
            resource_windows.append({
                "average_cpu_pct_of_2": round((last_cpu - window_cpu) / duration / USEC_PER_CPU_PERCENT, 1)
                if duration else None,
                "peak_sampled_MiB": round(peak_bytes / 2**20, 1) if peak_bytes else None,
            })
        elapsed = CLOCK() - begin
        cpu_percent = (cpu() - cpu0) / elapsed / USEC_PER_CPU_PERCENT
        stalls = {key: round((val - initial_pressure[key])/elapsed/10000, 2) for key, val in pressure().items()}
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = collections.Counter(str(e) for e in results if isinstance(e, BaseException))

        def pct(values, fraction):
            return round(sorted(values)[math.ceil(len(values) * fraction) - 1], 1)
        profile = {}
        for kind, metrics in self.profiles.items():
            profile[kind] = {label: {"p50_ms": pct(v, .50), "p95_ms": pct(v, .95),
                                     "p99_ms": pct(v, .99), "max_ms": round(max(v), 1),
                                     "seconds": round(sum(v)/1000, 2)} for label, v in metrics.items()}
        return {
            "wsgi_profile": profile,
            "resources_by_third": resource_windows,
            **({"recovery": {
                "learners_after_drop": self.step_down_to,
                "drop_after_measured_seconds": round(self.cutover - self.start, 2),
                "last_pre_drop_request_finished_after_seconds": round(self.drain_seconds, 3),
                "samples": self.recovery_samples,
                "answer_p95_by_start_second_from_drop_ms": {
                    k: pct(values, .95) for k, values in sorted(self.recovery_answers.items())
                },
            }} if self.step_down_to is not None else {}),
            "pressure_stall_pct": stalls,
            "max_monitor_lag_ms": round(monitor_lag * 1000, 1),
            "seconds": round(elapsed, 1),
            "responding_learners": len(self.responded),
            "rounds_finished": self.completed,
            "exhausted_queues": self.exhausted,
            "answer_p95_by_third_ms": [pct(window, .95) if window else None for window in self.answer_windows],
            "mirror_frames": self.mirror_frames,
            "reused_mirror_frames": self.reused_frames,
            "direct_users_with_reuse": len(self.direct_users_served),
            "mirror_response_bytes": self.mirror_bytes,
            "expired_previous_step_presence": self.expired_frames,
            "failed_viewers": dict(self.viewer_errors),
            "cpu_pct_of_2": round(cpu_percent, 1),
            "cpu_p95_one_second_pct": pct(cpu_samples, .95),
            "peak_sampled_MiB": round(memory / 2**20, 1),
            "errors_including_warmup": dict(self.errors),
            "failed_learners": dict(errors),
            "confirmed_including_warmup": self.confirmed,
            "http": {
                kind: {"n": len(times), "p50_ms": pct(times, .50),
                       "p95_ms": pct(times, .95), "p99_ms": pct(times, .99)}
                for kind, times in self.latencies.items()
            },
        }


def verify_shared_host(group, unit, lab, cores, workers, postgres):
    master = int(subprocess.check_output(
        ["systemctl", "--user", "show", unit, "-p", "MainPID", "--value"], text=True))
    postmaster = int((lab / "pgdata" / "postmaster.pid").read_text().splitlines()[0]) if postgres else None

    def children(pid):
        return set(map(int, Path(f"/proc/{pid}/task/{pid}/children").read_text().split()))

    for _ in range(100):
        worker_pids = children(master) - {postmaster}
        if len(worker_pids) == workers:
            break
        time.sleep(.05)
    if len(worker_pids) != workers:
        raise RuntimeError("Gunicorn worker count did not match the trial configuration.")
    expected = {master, *worker_pids}
    if postmaster:
        expected.update({postmaster, *children(postmaster)})
    members = set(map(int, (group / "cgroup.procs").read_text().split()))
    if not expected <= members or any(os.sched_getaffinity(pid) != set(cores) for pid in expected):
        raise RuntimeError("The service processes did not share the trial cgroup and CPU affinity.")
    quota, period = map(int, (group / "cpu.max").read_text().split())
    memory_max = int((group / "memory.max").read_text())
    swap_max = int((group / "memory.swap.max").read_text())
    if quota != 2 * period or memory_max != 8 * 2**30 or swap_max != 0:
        raise RuntimeError("The trial resource limits did not take effect.")
    return {"verified_gunicorn_workers": len(worker_pids), "postgres_in_same_group": bool(postmaster),
            "cpu_quota_vcpus": quota / period, "shared_cpu_ids": cores,
            "group_memory_max_bytes": memory_max, "group_swap_max_bytes": swap_max}


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--learners", type=int, required=True)
    args.add_argument("--step-down-to", type=int, help="Retain this many learners after one third of the measurement window")
    args.add_argument("--seconds", type=int, default=60)
    args.add_argument("--watched-percent", type=int, default=0)
    args.add_argument("--direct-percent", type=int, default=0, help="Established direct connections among parents watching")
    args.add_argument("--ramp", type=int, default=8, help="Seconds over which learners arrive")
    args.add_argument("--settle", type=int, default=4, help="Additional warm-up seconds after arrivals")
    args.add_argument("--relay-cache-entries", type=int, help="Override the relay cache limit in the test copy")
    args.add_argument("--admission", choices=("native", "fifo", "answers-first"), default="native",
                      help="Model a shared request queue in the generator with one slot per worker")
    args.add_argument("--profile", action="store_true", help="Time queueing, Django, and database operations inside the test service")
    args.add_argument("--workers", type=int, choices=range(1, 9), default=3)
    args.add_argument("--wal", action="store_true", help="Test SQLite WAL with full commit durability")
    args.add_argument("--analyze-fixture", action="store_true",
                      help="Populate PostgreSQL planner statistics after bulk-seeding synthetic histories")
    args.add_argument("--postgres-bin", type=Path, help="Initialize a temporary cluster using these server binaries")
    args.add_argument("--connection-age", type=int, default=0, help="Django database connection lifetime in seconds")
    args.add_argument("--idle-poll", type=float, default=2.5,
                      help="Simulated seconds between co-view availability checks when nobody is watching")
    a = args.parse_args()
    if a.step_down_to is not None and not 0 <= a.step_down_to < a.learners:
        args.error("The reduced cohort must be smaller than the starting cohort.")
    if not 1 <= a.idle_poll <= 8:
        args.error("Choose an idle polling interval of 1–8 seconds.")
    if a.analyze_fixture and not a.postgres_bin:
        args.error("--analyze-fixture requires PostgreSQL.")
    if a.postgres_bin and a.wal:
        args.error("--wal applies to SQLite.")
    if a.connection_age < 0:
        args.error("Choose a nonnegative connection lifetime.")
    if not 0 <= a.direct_percent <= 100:
        args.error("Direct connection share must be between 0 and 100 percent.")
    if a.relay_cache_entries is not None and a.relay_cache_entries < 1:
        args.error("The relay cache must allow at least one entry.")
    if not (1 <= a.ramp <= 45 and 1 <= a.settle <= 15 and a.ramp + a.settle + a.seconds <= 150):
        args.error("Choose a ramp of 1–45 s and settle of 1–15 s, with at most 150 s total.")
    if not (1 <= a.learners <= 1024 and 15 <= a.seconds <= 120 and 0 <= a.watched_percent <= 100):
        args.error("Choose 1–1024 learners, 15–120 seconds and 0–100 percent watched.")
    cores, generator = application_cpus()
    unit = "garden-capacity-" + secrets.token_hex(5)
    with tempfile.TemporaryDirectory(prefix="lg-capacity-") as tmp:
        lab = Path(tmp)
        (lab / ".capacity-lab").touch()
        for name in ("garden", "pilot", "templates"):
            shutil.copytree(REPO / name, lab / name, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("content", "static"):
            (lab / name).symlink_to(REPO / name)
        shutil.copy(REPO / "qa" / "capacity_fixture.py", lab / "fixture.py")
        (lab / "capacity_settings.py").write_text(
            'from garden.local_settings import *\n'
            'LOGGING = {"version": 1, "disable_existing_loggers": False, '
            '"handlers": {"trial": {"class":"logging.FileHandler","filename":BASE_DIR / "errors.log"}}, '
            '"loggers":{"django.request":{"handlers":["trial"],"level":"ERROR","propagate":False}}}\n')
        if a.relay_cache_entries:
            with (lab / "capacity_settings.py").open("a") as config:
                config.write(f'CACHES["coview"]["OPTIONS"] = {{"MAX_ENTRIES": {a.relay_cache_entries}}}\n')
        env = {"PATH":os.environ["PATH"], "DJANGO_SETTINGS_MODULE":"capacity_settings", "GARDEN_DEV":"0",
               "GARDEN_SECRET_KEY":secrets.token_urlsafe(40), "PYTHONPATH":os.environ.get("PYTHONPATH", "")}
        launcher = []
        with (lab / "capacity_settings.py").open("a") as config:
            if a.postgres_bin:
                shutil.copy(REPO / "qa" / "capacity_postgres.py", lab / "pg_service.py")
                if a.analyze_fixture:
                    env["CAPACITY_ANALYZE_FIXTURE"] = "1"
                launcher = ["pg_service.py", str(a.postgres_bin.resolve()), str(a.learners)]
                config.write('DATABASES["default"] = {"ENGINE":"django.db.backends.postgresql",'
                             '"NAME":"postgres","USER":"garden_capacity","HOST":str(BASE_DIR),"PORT":5432}\n')
            config.write(f'DATABASES["default"]["CONN_MAX_AGE"] = {a.connection_age}\n')
        if not a.postgres_bin:
            subprocess.run([sys.executable, "fixture.py", str(a.learners)], cwd=lab, env=env, check=True)
        if a.profile:
            shutil.copy(REPO / "qa" / "capacity_probe.py", lab / "capacity_probe.py")
        if a.wal:
            with sqlite3.connect(lab / "db.sqlite3") as db:
                if db.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                    raise RuntimeError("Could not enable WAL on the test database.")
            with (lab / "capacity_settings.py").open("a") as config:
                config.write('DATABASES["default"]["OPTIONS"] = {"init_command": "PRAGMA synchronous=FULL"}\n')
        cmd = ["systemd-run","--user","--quiet","--collect","--unit="+unit,"--working-directory="+str(lab),
               "-p","CPUQuota=200%","-p","MemoryMax=8G","-p","MemorySwapMax=0","-p","RuntimeMaxSec=5min",
               "taskset","-c",",".join(map(str,cores)), "/usr/bin/env","-i", *[f"{k}={v}" for k,v in env.items()],
               sys.executable,*launcher,"-m","gunicorn","--workers",str(a.workers),"--bind","unix:"+str(lab/"app.sock"),
               "--error-logfile",str(lab/"server.log"), "capacity_probe:application" if a.profile else "garden.wsgi:application"]
        try:
            subprocess.run(cmd, check=True)
            for tick in range(1200 if a.postgres_bin else 100):
                if (lab / "app.sock").exists():
                    break
                if tick and tick % 20 == 0:
                    active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit])
                    if active.returncode:
                        break
                time.sleep(.1)
            if not (lab / "app.sock").exists():
                log = lab / "server.log"
                message = log.read_text()[-1500:] if log.exists() else "Check the systemd user journal."
                raise RuntimeError("Benchmark server did not start. " + message)
            cg = subprocess.check_output(["systemctl","--user","show",unit,"-p","ControlGroup","--value"],text=True).strip()
            group = Path("/sys/fs/cgroup") / cg.lstrip("/")
            limits = verify_shared_host(group, unit, lab, cores, a.workers, bool(a.postgres_bin))
            if generator:
                os.sched_setaffinity(0,generator)
            families = json.loads((lab / "families.json").read_text())
            admission = None if a.admission == "native" else AdmissionQueue(a.workers, a.admission)
            trial = Trial(lab, a.seconds, a.ramp, a.settle, a.idle_poll, admission, a.step_down_to)
            result = asyncio.run(trial.run(families, a.watched_percent, a.direct_percent, group))
            result["verified_host"] = limits
            if a.postgres_bin:
                import psycopg
                database = psycopg.connect(host=str(lab), port=5432, dbname="postgres", user="garden_capacity")
                result["postgres_version"] = database.info.server_version
                backend = database.info.backend_pid
                if backend not in set(map(int, (group / "cgroup.procs").read_text().split())):
                    raise RuntimeError("PostgreSQL query backend was outside the tested resource group.")
                result["verified_host"]["query_backend_in_same_group"] = True
            else:
                database = sqlite3.connect(lab / "db.sqlite3")
            with database as db:
                if a.postgres_bin:
                    with db.cursor() as cursor:
                        cursor.execute("""
                            SELECT relname, extract(epoch FROM greatest(last_analyze, last_autoanalyze))
                            FROM pg_stat_user_tables WHERE schemaname = 'public'
                        """)
                        measured_start_epoch = time.time() - (CLOCK() - trial.start)
                        result["postgres_last_analyze_seconds_from_trial_start"] = {
                            name: round(float(epoch) - measured_start_epoch, 1) if epoch else None
                            for name, epoch in cursor.fetchall()
                        }
                stored = db.execute("select count(*) from pilot_questionattempt").fetchone()[0]
            log = (lab/"errors.log").read_text()
            if (group / "memory.peak").exists():
                result["whole_service_peak_MiB"] = round(int((group / "memory.peak").read_text()) / 2**20, 1)
            events = dict(line.split() for line in (group / "memory.events").read_text().splitlines())
            result["oom_kills"] = int(events["oom_kill"])
            result.update(analyzed_fixture=a.analyze_fixture, admission_policy=a.admission, idle_poll_seconds=a.idle_poll, database="postgresql" if a.postgres_bin else "sqlite", connection_age=a.connection_age,
                          workers=a.workers, sqlite_wal=a.wal, direct_percent_of_viewers=a.direct_percent,
                          relay_cache_override=a.relay_cache_entries, learners=a.learners, ramp_seconds=a.ramp,
                          settle_seconds=a.settle, watched_percent=a.watched_percent, server_cpus=cores,
                          separate_generator=bool(generator), persisted_attempts=stored,
                          sqlite_lock_messages=log.count("django.db.utils.OperationalError: database is locked"))
            print(json.dumps(result), flush=True)
        finally:
            subprocess.run(["systemctl","--user","stop",unit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
