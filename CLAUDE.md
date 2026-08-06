# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python simulator (in Portuguese comments/logs, TCC/thesis project) that models autoscaling behavior under normal load and EDoS-style (Economic Denial of Sustainability) HTTP flood attacks. It spins up a target web app as Docker containers, drives traffic against them, autoscales based on CPU, and logs metrics/RTT/packet captures for later analysis (entropy, plots).

There is no test suite, linter, or build step in this repo — it's an experimental/research harness, run directly with Python. Docker must be installed and running, and the simulation needs privileges to run `tcpdump` and (per `run_experiments.py`) is often invoked with `sudo`.

## Running the simulator

```bash
pip install -r requirements.txt   # docker, requests (pandas/numpy/matplotlib also needed for analysis/plot scripts, not pinned)

# single run
python main_orchestrator.py [--rps FLOAT] [--attackers INT] [--duration INT]

# sweep across RPS values (rebuilds/reuses image each run, needs sudo for tcpdump)
python run_experiments.py

# post-processing
python analyze_traffic.py   # reads rtt_log.csv -> rtt_entropy.csv (RTT Shannon entropy per time window)
python plot_graphs.py       # reads a CSV from experiment_results/ (edit CSV_FILE constant) -> graficos/*.png
```

There's no automated test runner; the self-test blocks under `if __name__ == "__main__":` in `docker_manager.py`, `autoscaler_logic.py`, `normal_traffic.py`, and `traffic_injectorV0.py` are the closest thing to tests — run a module directly (e.g. `python docker_manager.py`) to exercise it standalone. These self-tests actually build the Docker image and start/stop real containers, so Docker must be running.

All tunables (simulation duration, CPU thresholds, attack timing, work-unit intensity, ports, network name, log file names) live in `config.py` — check there first before changing behavior in other modules.

## Architecture

`main_orchestrator.py` is the single entry point and owns the whole simulation loop; every other module is a passive service it calls into on a fixed tick (`config.MONITOR_INTERVAL_SECONDS`, drift-corrected via `time.monotonic()` + `next_tick`). Per iteration it:

1. Refreshes container stats via `StatsCollector` (background-polling thread, `stats_collector.py`) — CPU% and app memory (usage minus page cache) per container, averaged across active instances.
2. Asks `autoscaler_logic.Autoscaler.decide_scaling(avg_cpu, num_instances)` for `SCALE_UP` / `SCALE_DOWN` / `NO_ACTION`, applies it via `docker_manager.start_instance()` / `stop_instance()`, and updates the autoscaler's cooldown state (`record_scale_action`).
3. Re-derives each active container's published host port (via `container.reload()` + `NetworkSettings`) to build target URLs, then drives traffic:
   - Normal traffic (`normal_traffic.start_http_traffic` / `stop_http_traffic`) — steady low-rate background load, round-robin across instances, tags requests with `?work=<NORMAL_WORK_UNITS>&sleep=<NORMAL_SLEEP>`.
   - Attack traffic (`traffic_injectorV0.start_http_flood` / `stop_http_flood`) — an EDoS-style **pulsed** flood scheduled by `ATTACK_START_TIME_SECONDS`/`PULSE_DURATION`/`SCALE_COOLDOWN_SECONDS`, tags requests with `?work=<ATTACK_WORK_UNITS>&sleep=<ATTACK_SLEEP>`. The injector is restarted whenever the instance count changes mid-attack so load stays spread across the current fleet. Note there is also a `traffic_injector.py` with an equivalent-but-different (non-pulsed, `duration_seconds`-based) attack API — the orchestrator currently imports `traffic_injectorV0`, not `traffic_injector`; check which one is actually wired up before editing "the" injector.
   - Both injectors are thread-pool-based (`daemon` threads, one per attacker/client, target RPS maintained via measured sleep intervals) and record round-trip times into module-level lists; `get_average_rtt_ms()` / `get_average_rtt_attack_ms()` drain those lists each time they're called (call-and-reset semantics, not a running average).
4. Logs one row per iteration to `config.METRICS_LOG_FILE` (elapsed time, instance count, avg CPU/mem/RTT, decision, active container names, `label` normal/attack) and appends to `instance_intervals_for_cost` for the end-of-run fictional cost total (`cost_calculator.py`).
5. A `TcpdumpSniffer` (`tcpdump_sniffer.py`) runs for the whole simulation as a separate `tcpdump` subprocess, parsing live packet lines into `config.TCPDUMP_OUTPUT_CSV` and stamping each row with whatever label (`benign`/`attack`) the orchestrator has set via `sniffer.set_label()` at that point in the loop — this is the ground-truth label for downstream traffic-classification work.

The target application under test is `app/simple_server.py`, a single-threaded-per-request stdlib `ThreadingHTTPServer` whose per-request CPU cost and latency are controlled purely by query params (`?work=N&sleep=S`, defaulting to env vars `WORK_UNITS`/`PROCESSING_TIME`) — `work` runs a tight `math.sqrt`/`math.sin` loop N times to burn CPU deterministically, `sleep` adds fixed latency. It's built into the `edos_target_app` image via the root `dockerfile` and run as `target_instance_N` containers on a dedicated bridge network (`config.DOCKER_NETWORK_NAME`), one published host port per instance starting at `STARTING_HOST_PORT`.

`docker_manager.py` wraps the Docker SDK for image build, network setup, container lifecycle, and cleanup (`cleanup_all_simulation_instances`, filtered by `BASE_CONTAINER_NAME` prefix — safe to call repeatedly, won't touch unrelated containers). It exposes both an SDK-stats CPU reader (`get_container_stats`, single snapshot) and a `docker stats --no-stream` CLI-based fallback (`get_container_cpu_percent`); the orchestrator's live metrics actually come from `StatsCollector`'s own polling loop in `stats_collector.py`, which duplicates the CPU% formula independently.

`analyze_traffic.py` and `plot_graphs.py` are standalone offline analysis scripts (not imported by the orchestrator) that consume the CSVs produced by a run — RTT entropy per time window and CPU/instance/memory time-series plots respectively. Hardcoded filenames at the top of each (`INPUT_FILE`, `CSV_FILE`) need to be edited by hand to point at a specific run's output before use.

`main_orchestrator_back.py` is a backup/older version of the orchestrator kept alongside the current one — don't confuse the two; the current entry point is `main_orchestrator.py`.

Three sweep scripts drive `main_orchestrator.py` via its CLI overrides (`--rps`, `--attackers`, `--work-units`, `--attack-duration`, `--normal-rps`, `--normal-work-units`, `--attack-start`, `--pulse-duration`) and move its output CSVs into `experiment_results/` with scenario-specific filenames: `run_experiments.py` (attack-only, sweeps RPS × attackers × work units), `run_experiments_normal.py` (normal-traffic-only baselines, `--attack-duration 0`), and `run_experiments_combined.py` (normal + attack overlay together, attack volume expressed as a percentage of the normal scenario's request volume). **`rtt_log.csv` is not part of this per-scenario saving** — none of the three sweep scripts move/rename it, so it only ever contains the most recent run's RTT samples and gets silently overwritten by whatever ran last, sweep or standalone.

`EntCusumZV3.py` is a standalone, offline statistical-analysis script (Phase 3.5 tooling, not imported by the orchestrator) that reads `rtt_log.csv` and runs a sliding-window burst detector over it: for each window (`window_seconds=20` default, `overlap_percent=50` → 10s stride) it computes Shannon entropy of the RTT distribution, a Z-score against the *previous* window's mean/std, and a classic one-sided CUSUM statistic (accumulated per-sample across the whole file, using `global_mean`/`global_std` computed once over the *entire* file as the baseline). A window is flagged `'DDoS Burst'` when its mean RTT exceeds `min_rtt_burst` (default 50ms) and either the Z-score or CUSUM alarm fires. Outputs a printed table, `rtt_bursts_tunaveis.xlsx`, and `rtt_todos_bursts.png`. Known caveats worth knowing before trusting its output: (1) the CUSUM baseline is computed from the whole file, so if normal+attack periods are mixed in one `rtt_log.csv`, the "in-control" reference is itself contaminated by the attack, which can reduce sensitivity; (2) the plot's shaded "expected interval" is hardcoded to `axvspan(20, 100)`, which no longer matches the current attack window (`ATTACK_START_TIME_SECONDS` + `PULSE_DURATION` — currently `[20, 160]`, not `[20, 100]`); (3) it has no awareness of the `label` column in `simulation_metrics.csv` or `traffic_capture.csv`, so it can't self-report TPR/FPR against ground truth — that comparison has to be done by eye against those files' timestamps.

## Known inconsistencies to be aware of

- `config.py` has accumulated parameters over several iterations of the experiment design (e.g. both an old `HTTP_ATTACK_*` flat-rate attack config and a newer `EDOS_PULSE_*`/`EDOS_IDLE_*`/`EDOS_SATURATION_*` pulsed-attack config exist side by side; only some are actually read by the current `main_orchestrator.py`). Grep for a constant's usage across the repo before assuming it's live.
- `traffic_injector.py` vs `traffic_injectorV0.py` and `main_orchestrator.py` vs `main_orchestrator_back.py` are parallel versions from different iterations — confirm which one is actually imported/run before modifying "the" version of either.
- `docs/*.md` describe an earlier version of the simulation (simpler flat-rate attack, `PROCESSING_TIME` env-var sleep in `simple_server.py`, function-based non-class `autoscaler_logic`) and no longer match the current code (class-based `Autoscaler`, work-unit-based CPU load, pulsed EDoS attack, tcpdump sniffing, stats collector thread). Treat them as historical context, not a spec.
