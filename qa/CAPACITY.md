# Little Garden lesson capacity

## Local sizing trial · November 23, 2026

**A 2-vCPU / 8 GiB host looks reasonable for the early pilot.** At 192 children plus 48 watching parents, co-located PostgreSQL and Django used 45.5% CPU and answer p95 was 25 ms. At 768 learners, an eight-second arrival burst against a freshly bulk-loaded database drove p95 to 2.49 seconds. Running PostgreSQL `ANALYZE` before the same burst brought p95 to 20 ms and average combined CPU to 63%. In a separate overloaded run, dropping from 768 to 192 learners cleared all pre-existing requests in 1.87 seconds. Use 100–200 simultaneous children as an initial planning range until the mixed workload has a longer run on the actual Linode.

### Capacity with parents watching and PostgreSQL statistics refreshed

**The 500 ms answer threshold fell between 512 and 576 active learners in the two-minute trials, with one parent watching per four learners.** An 8-second burst brought all learners online. After 12 more seconds, measurements ran for 75 seconds. One parent watched for every four learners. Half the viewers followed the established direct connection path and half used relay. The direct path models server traffic and scene reuse. The proportions are workload choices. Every run used a fresh database, `ANALYZE` after bulk loading, three synchronous workers, 60-second database connections and a 3,000-entry co-view cache. Django and PostgreSQL shared two CPUs and 8 GiB. These runs used native request handling with the profiler disabled.

| Learners | Watching parents | Answer p95 (ms) | Mirror request p95 (ms) | Combined CPU (%) | Peak sampled memory (MiB) |
|---:|---:|---:|---:|---:|---:|
| 384 | 96 | 25 | 20 | 78.2 | 263 |
| 512 | 128 | 285 | 278 | 97.6 | 271 |
| 576 | 144 | 485 / 491 | 479 / 487 | 98.3 / 98.3 | 291 / 291 |
| 608 | 152 | 637 / 595 | 630 / 592 | 97.9 / 98.1 | 292 / 293 |
| 640 | 160 | 698 | 691 | 98.2 | 294 |

Paired figures are independent repetitions of the same workload. The warning threshold is 500 ms for answer p95. At 576 learners, the last 25 seconds of the two ordinary runs reached 508 ms and 514 ms.

The longer runs used the same arrival pattern and database setup.

| Learners | Watching parents | Overall answer p95 | Answer p95 in successive 40-second windows | Combined CPU |
|---:|---:|---:|---|---:|
| 512 | 128 | 430 ms | 219 ms → 293 ms → 471 ms | 98.0% |
| 576 | 144 | 690 ms | 414 ms → 510 ms → 739 ms | 98.3% |

Every learner had assignments available through the end of both holds. At 384 learners with 96 parents the 75-second run still had about one fifth of CPU capacity available.

All 57,975 acknowledged attempts across the sweep and both holds were saved. Every learner answered and every simulated direct viewer exercised the scene-reuse path. At 640 learners, 8,493 of 8,693 mirror polls returned a frame. A missing frame can leave the parent displaying the previous one. The implementation's pilot cache default is 300 entries. The higher benchmark limit matters for applying these numbers in production.

To reproduce, use the PostgreSQL command below with `--analyze-fixture --watched-percent 25 --direct-percent 50 --relay-cache-entries 3000`, omit `--profile`, and change `--learners` to the desired cohort. Use `--seconds 120` for the two longer runs.

### Ordinary lessons on the pilot SQLite configuration

| Active learners | Arrival window | Answers per second | Answer p95 | Average CPU across 2 vCPUs | Peak sampled app memory |
|---:|---:|---:|---:|---:|---:|
| 16 | 8 s | 2.1 | 21 ms | 3.3% | 115 MiB |
| 64 | 8 s | 8.1 | 21 ms | 12.2% | 117 MiB |
| 192 | 8 s | 24.2 | 20 ms | 27.9% | 118 MiB |
| 384 | 8 s | 48.2 | 18 ms | 38.8% | 120 MiB |
| 512 | 8 s | 64.3 | 19 ms | 44.1% | 121 MiB |
| 640 | 8 s | 80.4 | 24 ms | 51.1% | 122 MiB |
| 768 | 8 s | 87.2 | 2,766 ms | 52.7% | 122 MiB |
| 768 | 45 s | 75.6 | 3,312 ms | 47.7% | 123 MiB |

At 640 learners the server completed 1,280 rounds in 90 seconds. In the slower-arrival 768-learner trial, the three successive 30-second answer p95s were 32 ms, 3.28 s and 3.76 s. The late slowdown persisted well after arrivals finished. Both 768-learner trials saved every acknowledged attempt and all learners continued answering. The measurements show latency pressure with substantial average CPU and memory headroom. The instrumented follow-up below measures where that time went. No SQLite lock errors appeared in the server error log for these trials.

### Parents watching

With 64 learners and 16 active relay viewers, all 1,049 measured mirror polls returned a frame and the answer p95 was 37 ms. At 192 learners and 48 relay viewers, 2,804 of 3,179 polls returned a frame (88.2%). All acknowledged learner submissions were saved. The benchmark also recorded 55 expired previous-step broadcasts during answer celebrations, including warm-up. A polling gap can leave the parent displaying an older frame.

The current file cache inherits Django’s 300-entry default. Repeating the 192-learner trial with its limit raised to 3,000 in the test copy yielded frames on **3,171 of 3,171** polls with zero expired previous-step broadcasts. Average CPU was 41.5% and peak sampled memory was 122 MiB. The evidence supports sizing the co-view cache before onboarding dozens of simultaneous viewers. These were benchmark settings. Two exploratory co-view runs stopped individual simulated clients when their previous-step broadcast expired. The driver now counts that response and advances to the next question like the browser. The reported trials use the corrected behavior.

### How much direct co-view changes server load

The same 192 learners and 48 watching parents ran for 45 seconds in each case. All three trials used the 3,000-entry cache so cache eviction would not obscure the comparison.

| Established direct links | Relay viewers | CPU | Answer p95 | Mirror response bodies per second |
|---:|---:|---:|---:|---:|
| 0 | 48 | 41.2% | 17 ms | 57.5 KiB |
| 24 | 24 | 41.2% | 18 ms | 39.0 KiB |
| 48 | 0 | 41.2% | 17 ms | 20.5 KiB |

All 48 assigned direct viewers exercised the app’s direct scene-reuse path in the last trial. HTTP mirror response bytes fell 64% between the endpoints. The child and parent still contact the server for session state, scene changes and signaling throughout direct viewing, which helps explain the similar CPU results. The peer channel carries interactive updates between browsers. The table covers application response bodies and excludes headers, encryption overhead and traffic between peers.

There is no measured field rate for this pilot. For planning, track both the share of viewing sessions that establish a direct channel and the share of active viewing seconds spent direct, including transitions back to relay. The second metric answers the capacity question. The app can count those durations without retaining network addresses or lesson contents.

### Where an answer waited

With 768 learners, three synchronous Gunicorn workers, and the default SQLite journal, the instrumented answer p95 was **2,744 ms**. The p95 from starting the local request to reaching the WSGI application was **2,708 ms**. Django processing p95 was **31 ms**, worker CPU p95 was **6 ms**, and time after Django prepared response headers was below **1 ms** at p95. The driver's one-second sampling timer was at most 1.1 ms late. This puts the multi-second delay before application processing, at admission to the worker pool. Each synchronous worker handles one request at a time. [Gunicorn worker design](https://docs.gunicorn.org/en/stable/design.html)

Across routes, 102.6 of 167.2 measured Django worker-seconds were spent executing SQLite statements or committing. This includes database CPU and waits. Individual answer writes reached 733 ms, even though no request failed with a database-lock error. Over the complete interval, answer submissions used 80.3 Django worker-seconds and co-view presence requests used 43.7. At 512 learners, presence checks accounted for 65% of all application requests, even with no parents watching.

### Sharing one machine with PostgreSQL

PostgreSQL 18.7, its background processes, and all three Gunicorn workers ran on the same two cores under one combined 200% CPU quota, one 8 GiB memory limit, and zero swap. The harness checked the process IDs, affinity, resource limits, and membership of a live SQL backend. A separate load generator supplied the families. PostgreSQL used its local Unix socket with fsync and synchronous commits enabled.

At 768 learners, switching the database alone did not clear the request queue. PostgreSQL and SQLite WAL both had three workers, a 60-second Django connection lifetime, durable commits, 12 seconds of settling after arrivals, and identical 75-second profiled workloads. PostgreSQL saved all 6,991 acknowledged submissions including warm-up. SQLite saved all 8,621. The simulated children waited for responses before continuing, so the faster service received more answers in the same time.

| 768 learners, ordinary 2.5-second idle checks | Answer p95 | Before Django p95 | Django p95 | Average CPU | Peak sampled memory |
|---|---:|---:|---:|---:|---:|
| SQLite WAL, 60-second connections | 13 ms | 3 ms | 11 ms | 48.9% | 127 MiB |
| PostgreSQL, 60-second connections | 2,446 ms | 2,401 ms | 63 ms | 80.8% | 287 MiB |

PostgreSQL write statements and commits took 4.6 ms and 4.1 ms at answer p95. Time spent on reads within an answer reached 53 ms at p95. Most of the end-to-end delay was waiting for a worker. Profiles time both execution and scheduling, so these observations alone cannot identify a specific slow SQL query.

Two other SQLite experiments help narrow the choices. Enabling WAL while retaining the default per-request connections brought answer p95 to 453 ms in one run. Increasing the worker count from three to six with the original journal yielded 66 ms in a profiled run and 2,548 ms in an unprofiled repeat. Worker count alone gave inconsistent results. The short WAL and connection-lifetime experiments warrant a longer trial with parent reports and realistic disk contention. [SQLite write-ahead logging](https://sqlite.org/wal.html)

### PostgreSQL operating points

All learners worked without a parent watching. Each answer, retry and question change still triggered a presence update. The five-second experiment changed only the periodic checks from an idle child. A parent opening the mirror between actions could wait up to 2.5 seconds longer for the child to notice. The active-viewer interval remained 650 ms.

| Learners | Idle check interval | Profiler | Answers/s | Answer p95 | Average combined CPU | Combined sampled memory | Saved attempts including warm-up |
|---:|---:|---|---:|---:|---:|---:|---:|
| 512 | 2.5 s | Off | 63.8 | 291 ms | 70.5% | 254 MiB | 4,718 / 4,718 |
| 768 | 2.5 s | On | 80.0 | 2,446 ms | 80.8% | 287 MiB | 6,991 / 6,991 |
| 768 | 5 s | On | 80.3 | 2,653 ms | 79.8% | 285 MiB | 7,045 / 7,045 |

At pilot size on PostgreSQL, **192 children and 48 watching parents** (24 direct and 24 relayed) used **45.5% combined CPU and 244 MiB** peak sampled memory. Answer p95 was **24.5 ms**, all **1,798 acknowledged attempts** were present, and all **3,172 mirror polls** returned a current frame. The test copy used a 3,000-entry co-view cache. The direct/relay split was an input to the experiment.

At 768 learners, stretching the idle interval cut presence requests from 21,059 to 15,854 (25%) while answer p95 stayed above two seconds. This result provides little reason to trade slower viewer discovery for capacity. The PostgreSQL delay also varied over time. Under ordinary polling, successive 25-second answer p95s were 2.42 s, 2.53 s and 22 ms. Families arrived over eight seconds. A longer run on the intended VPS with natural arrivals would distinguish sustained demand from a burst.

### The effect of fresh PostgreSQL statistics

With the ordinary eight-second arrival burst and 768 learners, a fresh database had seconds to absorb a bulk load of family, session, assignment and skill-history rows before play began. In instrumented runs without a manual statistics refresh, the PostgreSQL catalog recorded its first automatic analysis of those tables about 35–36 seconds into measurement. The drop from 768 to 192 learners in the recovery trial happened at 20 seconds. Its backlog cleared well before that analysis.

A matched repeat ran `ANALYZE` once after seeding, before Gunicorn accepted traffic. Answer p95 fell from **2,485 ms to 20 ms**. Average combined CPU fell from **81.8% to 63.0%** while completed answer requests rose from **80.4 to 96.9 per second**. Peak sampled memory was 288 MiB. All 8,611 acknowledged answers and retries were persisted. Answer p95 stayed between 19 and 21 ms in all three measurement intervals. One matched trial shows that preparing the database after a large import changes this result materially. It does not isolate individual SQL plans or the effect of warming database pages. PostgreSQL uses these statistics to choose how to execute queries. [PostgreSQL ANALYZE](https://www.postgresql.org/docs/18/sql-analyze.html)

For production sizing, test an established dataset with current statistics and keep a separate cold bulk-import trial. This experiment supports refreshing statistics after a large import and retaining three workers for the pilot. The fresh-fixture bursts alone would understate the steady performance observed on this hardware.

### More workers and staggered starts

Each run used 768 children, co-located PostgreSQL, durable commits, ordinary presence polling, and a 75-second measurement window after arrivals and a 12-second settling period. The first pair changes only the Gunicorn worker count. The third spreads arrivals over 45 seconds with the original three workers. CPU and answer data for each successive 25-second period are aligned.

| Workers | Arrival window | Overall answer p95 | Answer p95 by third | Combined CPU by third | Overall CPU | Peak sampled memory |
|---:|---:|---:|---|---|---:|---:|
| 3 | 8 s | 2,485 ms | 2,502 ms / 2,528 ms / 22 ms | 99.3% / 82.7% / 63.6% | 81.8% | 285 MiB |
| 6 | 8 s | 2,527 ms | 2,522 ms / 2,630 ms / 32 ms | 99.9% / 86.8% / 69.0% | 85.2% | 413 MiB |
| 3 | 45 s | 21 ms | 22 ms / 23 ms / 19 ms | 62.7% / 64.4% / 63.0% | 63.4% | 287 MiB |

Six workers delivered about 80 answers/s, as did three. Peak sampled memory rose from 285 to 413 MiB. With three workers and the 45-second ramp, all 768 continued playing through the final interval. The longer ramp also allowed the newly loaded database more time before measurement, making arrival spacing and warm-up difficult to separate in that comparison.

### Giving answers priority

The simulator tested two scheduling policies in front of the same three app workers. Both limited outstanding HTTP requests to three. One served requests in arrival order. The other admitted waiting answer submissions first, preserving arrival order within each class. Scheduling ran in the load generator as a model of a front-end queue. Timings start before entering the queue. The cost of running a production dispatcher on the VM is outside this experiment.

Both cohorts used 768 active children, private PostgreSQL, an eight-second arrival window, 12 seconds to settle, and 60 seconds of measured play. All other delays and client behavior were held fixed. Answer acknowledgments, next-question latency, and completed rounds show how moving a request forward affects the experience downstream.

| Admission order | Answer p95 | Next-question p95 | Presence p95 | Answer requests/s | Rounds finished | Average CPU | Saved / acknowledged including warm-up |
|---|---:|---:|---:|---:|---:|---:|---:|
| Arrival order | 2,423 ms | 2,394 ms | 2,368 ms | 75.5 | 772 | 85.0% | 5,514 / 5,514 |
| Answers first | 238 ms | 5,621 ms | 5,935 ms | 71.6 | 769 | 78.3% | 5,103 / 5,103 |

In the priority trial, the child saw the answer acknowledgment roughly ten times sooner at p95, then waited 5.62 seconds at p95 for the next question. Completed rounds were nearly equal. Moving only submitted answers ahead in the queue offered a poor end-to-end trade for this workload.

### Recovery after children stop playing

This test started with 768 learners, three workers and PostgreSQL. Twenty seconds into the measurement, 576 households stopped issuing new requests. All requests already submitted were allowed to finish. The other 192 learners kept playing for 40 seconds. At the drop, the server and app shared the same two CPUs. **The last request started before the drop finished 1.874 seconds later.** All 3,419 acknowledged attempts were saved. Requests in flight include those waiting for an app worker or a response, plus requests actively being processed.

| End of one-second interval relative to drop | Combined CPU in interval | Total requests in flight | Started before drop and still in flight | Answer p95 for starts in interval |
|---:|---:|---:|---:|---:|
| -2 s | 99.6% | 501 | 501 | 1,649 ms |
| -1 s | 99.6% | 547 | 547 | 1,796 ms |
| +0 s | 99.4% | 556 | 556 | 1,900 ms |
| +1 s | 98.9% | 320 | 235 | 1,881 ms |
| +2 s | 99.6% | 132 | 0 | 1,260 ms |
| +3 s | 96.2% | 0 | 0 | 530 ms |
| +4 s | 43.3% | 2 | 0 | 81 ms |
| +5 s | 44.7% | 1 | 0 | 47 ms |
| +10 s | 64.6% | 10 | 0 | 100 ms |
| +20 s | 31.7% | 0 | 0 | 19 ms |
| +30 s | 32.5% | 0 | 0 | 23 ms |

### Interpreting the results

P95 is the time by which 95% of submissions received an application response. The two-second celebration starts after that response. For this experiment the warning levels were a 500 ms answer p95, any failed or unaccounted-for answer, or 80% average CPU. These are planning thresholds. The driver models learners who wait for a response before continuing, so submission throughput can flatten when the app slows down.

The app and database shared two physical cores of an Intel i5-12600KF and local NVMe storage. Linux cgroup v2 enforced the limits. The app used Python 3.12, Django 5.2.19 and, by default, three synchronous Gunicorn 23.0.0 workers. The baseline used the app's existing SQLite configuration. Database and worker changes are identified in the comparison tables. The driver ran on other cores. Dates, authentication, scoring, and saved attempt history used app code at commit `e5b6ad6`. The home pilot remained available throughout.

The trials measure short periods of lesson activity. They exclude public-network latency, TLS, proxy and static-file delivery, simultaneous sign-ins, parent reporting, long histories, backups, and video or audio streaming. For scale, the direction clips referenced by the fixture averaged 13,264 bytes. At the 512-learner question rate, an uncached clip per question would add roughly 6.2 Mbit/s of outbound audio before protocol overhead. This is a byte-count estimate, separate from measured request timings.

A shared Linode can experience CPU contention from other instances. Run the same trial against the actual storage and CPU allocation before setting a public capacity target. On a small VM with the driver sharing the same cores, generator overhead also contributes to host load. [Akamai’s CPU allocation guide](https://techdocs.akamai.com/cloud-computing/docs/choosing-between-shared-and-dedicated-cpus)

## Workload

One active learner has a private session and keeps working through three- and five-question rounds. The driver reads the question page and its submission token, waits 5–8 seconds, submits an answer, waits through the two-second celebration, and opens the next question. Ten percent of questions get an incorrect first answer and a retry. Learners return to their garden between rounds. Fixtures rotate letter keys, number keys, and making ten. Each learner starts with ten completed rounds and fifty earlier skill samples.

The driver sends the child's normal presence requests during play. With the relay option, the selected parents poll every 900 ms and their children send full state every 650 ms while the server reports an active viewer. The relay returns rendered frames on parent polls. A stale broadcast during a previous question’s two-second celebration is counted separately, matching the browser’s continuation to the next question. The quiet-child interval is 2.5 seconds. This covers application requests through session authentication, CSRF validation, template rendering, database writes, scoring, and the new per-question history. The driver counts acknowledged attempts and checks the stored attempt count at the end.

## Repeating a trial

Run from the checkout on Linux with a systemd user manager and cgroup v2 CPU and memory controllers. Gunicorn is a benchmark dependency. One way to keep it separate from the app is to run:

```sh
bench_deps=$(mktemp -d)
.venv/bin/python -m pip install --target "$bench_deps" gunicorn==23.0.0
PYTHONPATH="$bench_deps" .venv/bin/python qa/capacity.py --learners 64 --seconds 60
PYTHONPATH="$bench_deps" .venv/bin/python qa/capacity.py --learners 64 --seconds 60 --watched-percent 25
```

Each invocation builds fresh synthetic households and, by default, a SQLite database on the temporary filesystem, starts three synchronous Gunicorn workers behind a private Unix socket, verifies the two-vCPU and 8 GiB limits, and removes the service and fixtures on exit. Use a disk-backed temporary directory for comparable SQLite write measurements. No family credentials or remote target are needed. The driver uses separate physical cores when available. On a two-vCPU VM the driver shares the host with the service.

For a transport comparison, `--direct-percent 50` assigns half of the watching parents to the established direct path. The driver sends the source and viewer identifiers, acknowledges the last displayed scene, and follows the server’s relay/metadata flag. It checks how many viewers received a scene-reuse response. The remaining parents use full server relay. The load generator models the server side of established connections. The separate Playwright co-view test opens actual browser data channels and exercises loss and fallback.

The final JSON includes latency by operation, resource use, completed rounds, errors, and persisted attempts. For co-view, compare mirror_frames to the number of mirror polls. An empty poll means the server had no current frame for that parent. By default, arrivals are spread across eight seconds followed by four more seconds of warm-up. Use `--ramp` and `--settle` to measure a different arrival pattern. Latencies cover the local request and response. CPU is a percentage of the two-core allowance. Memory is the largest one-second sample for the service cgroup, including workers and charged cache pages. The OS and driver have separate memory use.

For the bottleneck investigation, `--profile` wraps only the disposable service. It times client request initiation to WSGI entry, Django request processing to the response headers, worker CPU, cursor work, and database commits. Percentiles for different components describe different request distributions and cannot be added. Database time is included in Django time. `--workers 6` changes the size of the worker pool. `--wal` enables SQLite write-ahead logging with full synchronous commits in the temporary database. Holding the workload fixed lets each change be compared separately.

To compare PostgreSQL on the same server, supply a PostgreSQL server binary directory and install Psycopg 3 in the benchmark environment. The fixture initializes a private cluster that listens only on its temporary Unix socket. PostgreSQL, its query backends, and Gunicorn share the same systemd cgroup, CPU affinity, CPU quota, and memory cap. Startup verifies the postmaster, PostgreSQL child processes and app workers, and the final row count checks the query backend’s cgroup. The driver remains outside the shared allowance.

```sh
.venv/bin/python -m pip install --target "$bench_deps" 'psycopg[binary]>=3.2,<4'
PYTHONPATH="$bench_deps" .venv/bin/python qa/capacity.py --learners 768 --seconds 75 --settle 12 --profile --connection-age 60 --postgres-bin /usr/lib/postgresql/18/bin
PYTHONPATH="$bench_deps" .venv/bin/python qa/capacity.py --learners 768 --seconds 75 --settle 12 --profile --connection-age 60 --wal
```

Add `--idle-poll 5` to simulate five seconds between checks while nobody is watching. Keep the default 2.5 seconds to reproduce the current client. The comparison uses a 60-second Django connection lifetime for both backends so PostgreSQL connection establishment does not dominate short polling requests. [Django database connection management](https://docs.djangoproject.com/en/5.2/ref/databases/#persistent-connections)

The [per-trial results](capacity-results.json) include request counts, latency distributions, saved attempt counts, and the resource-limit checks recorded by the PostgreSQL trials.

To reproduce the worker and scheduling trials, add `--workers 6` or `--ramp 45` one at a time to the PostgreSQL command above. Use 60 measured seconds and compare `--admission fifo` with `--admission answers-first` for the admission-order trials. The default `--admission native` sends requests directly to the socket.

For a load step use `--learners 768 --seconds 60 --settle 12 --step-down-to 192` with the same PostgreSQL flags. The driver times outstanding work through completion and records one-second CPU, in-flight request counts and answer latency around the drop.

Add `--analyze-fixture` to the PostgreSQL command to collect planner statistics after loading the synthetic households and before starting the web workers. The output includes the most recent statistics refresh time by table relative to the measurement start.
