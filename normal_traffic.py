# normal_traffic.py
import threading
import time
import csv
import math
import os
from statistics import mean
import requests
from datetime import datetime

import config
import docker_manager

# cada execução gera um CSV separado para facilitar comparações
REPORTS_DIR = "normal_reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

REQUEST_TIMEOUT = getattr(config, "NORMAL_REQUEST_TIMEOUT_S", 5.0)

# padrões de requisições (ajuste se quiser no arquivo)
REQUEST_PATTERNS = getattr(config, "NORMAL_REQUEST_PATTERNS", [
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/?q=roma"),
    ("GET", "/static?id=1"),
    ("POST", "/echo"),
])

# parâmetros lidos do config.py (você os edita manualmente entre execuções)
DEFAULT_CLIENTS = getattr(config, "NORMAL_CLIENTS", 4)
DEFAULT_RPS_PER_CLIENT = getattr(config, "NORMAL_RPS_PER_CLIENT", 2)
DEFAULT_METRICS_SNAPSHOT_INTERVAL = getattr(config, "NORMAL_METRICS_SNAPSHOT_INTERVAL_S", 5)

# --- estado global controlado por start/stop ---
_stop_event = threading.Event()
_worker_threads = []
_rtt_lock = threading.Lock()
_rtt_values = []             # RTTS coletados durante a execução
_snapshot_lock = threading.Lock()
_snapshots = []              # lista de (timestamp, cpu_avg, mem_avg, cpu_time_total_s)

# utilitários
def _percentile(values, p):
    if not values:
        return 0.0
    values_sorted = sorted(values)
    k = (len(values_sorted)-1) * (p/100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values_sorted[int(k)]
    d0 = values_sorted[f] * (c-k)
    d1 = values_sorted[c] * (k-f)
    return d0 + d1

def _pick_target_url(target_urls, client_idx, req_idx):
    return target_urls[(client_idx + req_idx) % len(target_urls)]

def _issue_request(session, base_url, method, path):
    url = base_url + path
    start = time.perf_counter()
    try:
        if method == "GET":
            r = session.get(url, timeout=REQUEST_TIMEOUT)
        elif method == "POST":
            r = session.post(url, json={"hello":"roma"}, timeout=REQUEST_TIMEOUT)
        else:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
        status = r.status_code
        ok = True
    except requests.RequestException:
        status = -1
        ok = False
    rtt_ms = (time.perf_counter() - start) * 1000.0
    return rtt_ms, ok, status

def _client_loop(client_idx, rps, target_urls):
    """
    Loop contínuo por cliente: envia requisições à taxa (RPS) até _stop_event estar setado.
    Implementa pacing simples com sleep.
    """
    if rps <= 0:
        return
    sleep_interval = 1.0 / rps
    sess = requests.Session()
    req_idx = 0
    while not _stop_event.is_set():
        pattern = REQUEST_PATTERNS[req_idx % len(REQUEST_PATTERNS)]
        method, path = pattern
        base_url = _pick_target_url(target_urls, client_idx, req_idx)
        rtt_ms, ok, status = _issue_request(sess, base_url, method, path)
        with _rtt_lock:
            _rtt_values.append(rtt_ms)
        req_idx += 1
        # sleep curto; se stop_event for setado, sairá no próximo loop
        time.sleep(sleep_interval)

def _snapshotter(containers, interval_s):
    """
    Tira snapshots periódicos do cluster até _stop_event.
    Cada snapshot: (timestamp, cpu_avg_pct, mem_avg_mb, cpu_time_total_s)
    """
    while not _stop_event.is_set():
        cpu_avg, mem_avg, cpu_time_total = _snapshot_cluster_metrics(containers)
        with _snapshot_lock:
            _snapshots.append((int(time.time()), cpu_avg, mem_avg, cpu_time_total))
        # sleep, mas acorda mais cedo se stop_event for setado
        _stop_event.wait(timeout=interval_s)

def _snapshot_cluster_metrics(containers):
    cpu_pcts = []
    mem_mbs = []
    cpu_time_s_sum = 0.0
    for c in containers:
        try:
            c.reload()
            stats = docker_manager.get_container_stats(c)
            cpu_pcts.append(stats.get("cpu_percent", 0.0))
            mem_mbs.append(stats.get("memory_usage_mb", 0.0))
            cpu_time_s_sum += docker_manager.get_container_cpu_total_seconds(c)
        except Exception:
            pass
    avg_cpu = mean(cpu_pcts) if cpu_pcts else 0.0
    avg_mem = mean(mem_mbs) if mem_mbs else 0.0
    return avg_cpu, avg_mem, cpu_time_s_sum

# --- API pública: start/stop/report ---
def start_normal_traffic(target_urls,
                         clients=DEFAULT_CLIENTS,
                         rps_per_client=DEFAULT_RPS_PER_CLIENT,
                         metrics_snapshot_interval_s=DEFAULT_METRICS_SNAPSHOT_INTERVAL):
    """
    Inicia tráfego normal *contínuo* com os parâmetros lidos do config (ou passados).
    Devolve imediatamente; a execução segue em background até stop_normal_traffic() ser chamada
    ou até KeyboardInterrupt no processo que chamou start_*. 
    """
    global _worker_threads, _stop_event, _rtt_values, _snapshots
    if not target_urls:
        raise ValueError("target_urls é vazio. Forneça ao menos uma URL alvo.")

    # reset estado
    _stop_event.clear()
    _rtt_values = []
    _snapshots = []
    _worker_threads = []

    containers = docker_manager.get_active_instances_by_base_name()

    # iniciar snapshotter
    snap_thread = threading.Thread(target=_snapshotter, args=(containers, metrics_snapshot_interval_s), daemon=True)
    snap_thread.start()
    _worker_threads.append(snap_thread)

    # iniciar clients
    for i in range(clients):
        t = threading.Thread(target=_client_loop, args=(i, rps_per_client, target_urls), daemon=True)
        t.start()
        _worker_threads.append(t)

    print(f"[NormalTraffic] Iniciado: {clients} clients × {rps_per_client} RPS/cliente. Para parar: chame stop_normal_traffic() ou interrompa o processo (Ctrl+C).")

def stop_normal_traffic_and_report(scenario_name=None, out_dir=REPORTS_DIR):
    """
    Para os workers, consolida métricas e gera CSV de relatório (nome com timestamp).
    Retorna o dicionário resumo.
    """
    # sinaliza parada e aguarda threads encerrarem (daemon threads terminarão quando o processo acabar,
    # aqui esperamos um breve tempo para garantir que threads terminem loops)
    _stop_event.set()
    # aguardar um curto período para flush de requisições em andamento
    time.sleep(0.5)

    # snapshots finais: pegar containers e uma última coleta
    containers = docker_manager.get_active_instances_by_base_name()
    final_cpu, final_mem, final_cpu_time = _snapshot_cluster_metrics(containers)
    with _snapshot_lock:
        _snapshots.append((int(time.time()), final_cpu, final_mem, final_cpu_time))

    # consolidar RTTs
    with _rtt_lock:
        rtts = list(_rtt_values)

    rtt_avg = round(mean(rtts), 3) if rtts else 0.0
    rtt_p95 = round(_percentile(rtts, 95), 3) if rtts else 0.0
    rtt_max = round(max(rtts), 3) if rtts else 0.0

    # consolidar snapshots (média das médias)
    with _snapshot_lock:
        snaps = list(_snapshots)
    cpu_avgs = [s[1] for s in snaps] if snaps else []
    mem_avgs = [s[2] for s in snaps] if snaps else []
    cpu_time_last = snaps[-1][3] if snaps else final_cpu_time

    cpu_avg_of_snapshots = round(mean(cpu_avgs), 3) if cpu_avgs else round(final_cpu, 3)
    mem_avg_of_snapshots = round(mean(mem_avgs), 3) if mem_avgs else round(final_mem, 3)

    timestamp = int(time.time())
    timestr = datetime.utcfromtimestamp(timestamp).strftime("%Y%m%d_%H%M%S")
    scenario = scenario_name or f"normal_{timestr}"
    filename = os.path.join(out_dir, f"{scenario}.csv")

    # escrever CSV com um sumário + linhas de snapshot para análise detalhada
    with open(filename, "w", newline="") as f:
        w = csv.writer(f)
        # cabeçalho sumário
        w.writerow(["scenario", scenario])
        w.writerow(["generated_at_unix", timestamp])
        w.writerow(["rtt_avg_ms", rtt_avg])
        w.writerow(["rtt_p95_ms", rtt_p95])
        w.writerow(["rtt_max_ms", rtt_max])
        w.writerow(["cpu_avg_pct", cpu_avg_of_snapshots])
        w.writerow(["cpu_time_total_s", round(cpu_time_last,3)])
        w.writerow(["mem_avg_mb", mem_avg_of_snapshots])
        w.writerow([])
        w.writerow(["# Detailed snapshots: timestamp, cpu_avg_pct, mem_avg_mb, cpu_time_total_s"])
        w.writerow(["ts_unix","cpu_avg_pct","mem_avg_mb","cpu_time_total_s"])
        for s in snaps:
            w.writerow([s[0], s[1], s[2], round(s[3],3)])
        w.writerow([])
        w.writerow(["# RTT samples (ms)"])
        # limite de amostras no CSV para evitar arquivos gigantes (opcional)
        max_rtt_dump = getattr(config, "NORMAL_MAX_RTT_DUMP", 10000)
        dumped = rtts[:max_rtt_dump]
        w.writerow(["rtt_samples_count", len(rtts)])
        w.writerow(["rtt_sample_head(100)", dumped[:100]])

    summary = {
        "scenario": scenario,
        "report_file": filename,
        "rtt_avg_ms": rtt_avg,
        "rtt_p95_ms": rtt_p95,
        "rtt_max_ms": rtt_max,
        "cpu_avg_pct": cpu_avg_of_snapshots,
        "cpu_time_total_s": round(cpu_time_last,3),
        "mem_avg_mb": mem_avg_of_snapshots,
        "snapshots_count": len(snaps),
        "rtt_samples": len(rtts),
    }

    print(f"[NormalTraffic] Parado. Relatório gerado: {filename}")
    print("[NormalTraffic] Resumo:", summary)
    return summary
