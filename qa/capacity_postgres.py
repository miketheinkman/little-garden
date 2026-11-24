"""Start a Unix-socket-only PostgreSQL fixture and Gunicorn in the same cgroup."""
import os
from pathlib import Path
import subprocess
import sys
import time

import psycopg

lab = Path.cwd()
if not (lab / ".capacity-lab").is_file() or not lab.name.startswith("lg-capacity-"):
    raise RuntimeError("A private benchmark directory is required.")
binaries = Path(sys.argv[1])
learners = sys.argv[2]
data = lab / "pgdata"
with (lab / "server.log").open("ab", buffering=0) as log:
    subprocess.run([binaries / "initdb", "-D", data, "-U", "garden_capacity", "--no-locale", "-E", "UTF8",
                    "--auth-local=trust", "--auth-host=reject"], stdout=log, stderr=log, check=True)
    server = subprocess.Popen([binaries / "postgres", "-D", data, "-k", lab, "-h", "", "-p", "5432",
                               "-c", "fsync=on", "-c", "synchronous_commit=on"], stdout=log, stderr=log)
    for _ in range(200):
        if server.poll() is not None:
            raise RuntimeError("Fixture database stopped before readiness.")
        try:
            with psycopg.connect(host=str(lab), port=5432, dbname="postgres", user="garden_capacity"):
                break
        except psycopg.OperationalError:
            time.sleep(.1)
    else:
        raise RuntimeError("Fixture database did not become ready.")
    subprocess.run([sys.executable, "fixture.py", learners], stdout=log, stderr=log, check=True)
    if os.environ.get("CAPACITY_ANALYZE_FIXTURE") == "1":
        with psycopg.connect(host=str(lab), port=5432, dbname="postgres", user="garden_capacity", autocommit=True) as db:
            db.execute("ANALYZE")
# PostgreSQL remains in this transient service when its main process becomes Gunicorn.
os.execv(sys.executable, [sys.executable, *sys.argv[3:]])
