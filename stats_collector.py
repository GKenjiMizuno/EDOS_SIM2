import time
import threading
from typing import Dict, List, Optional, Tuple
import docker

try:
    import config  # usa o mesmo config do projeto, se existir
    POLL_INTERVAL = getattr(config, "DOCKER_STATS_POLL_INTERVAL_SECONDS", 1.0)
except Exception:
    POLL_INTERVAL = 1.0  # fallback

class StatsCollector:
    """
    Thread que coleta docker stats periodicamente e guarda num cache thread-safe.
    O loop principal lê somente desse cache (sem fazer chamadas ao Docker).
    """
    def __init__(self, client: Optional[docker.DockerClient] = None, poll_interval: float = POLL_INTERVAL):
        self.client = client or docker.from_env()
        self.poll_interval = poll_interval

        self._container_ids: List[str] = []  # lista de IDs (ou names) a monitorar
        self._cache: Dict[str, dict] = {}    # id -> métricas calculadas
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()

        self._t = threading.Thread(target=self._run, name="DockerStatsCollector", daemon=True)

    # --------- API pública ---------
    def start(self):
        self._t.start()

    def stop(self, timeout: Optional[float] = 2.0):
        self._stop_evt.set()
        self._t.join(timeout=timeout)

    def update_containers(self, containers: List):
        """
        Recebe objetos docker.Container OU strings (IDs/names).
        Guarda apenas os IDs para consulta interna.
        """
        ids = []
        for c in containers:
            ids.append(c.id if hasattr(c, "id") else str(c))
        with self._lock:
            self._container_ids = ids
            # remove do cache quem saiu
            self._cache = {cid: v for cid, v in self._cache.items() if cid in ids}

    def get_snapshot(self) -> Dict[str, dict]:
        """
        Retorna uma cópia rasa do cache: {container_id: {name, cpu_percent, mem_app_mb, raw_mem_usage, cache_mem}}
        """
        with self._lock:
            return {k: v.copy() for k, v in self._cache.items()}

    def get_averages(self) -> Tuple[float, float, List[str]]:
        """
        Retorna (avg_cpu_percent, avg_mem_app_mb, container_names)
        """
        snap = self.get_snapshot()
        if not snap:
            return 0.0, 0.0, []
        cpu = [v.get("cpu_percent", 0.0) for v in snap.values()]
        mem = [v.get("mem_app_mb", 0.0) for v in snap.values()]
        names = [v.get("name", "") for v in snap.values()]
        return (sum(cpu) / len(cpu), sum(mem) / len(mem), names)

    # --------- Loop interno ---------
    def _run(self):
        while not self._stop_evt.is_set():
            ids = self._copy_ids()
            for cid in ids:
                try:
                    c = self.client.containers.get(cid)
                    stats = c.stats(stream=False)
                    metrics = self._compute_metrics(c, stats)
                    if metrics:
                        with self._lock:
                            self._cache[cid] = metrics
                except docker.errors.NotFound:
                    with self._lock:
                        self._cache.pop(cid, None)
                except Exception:
                    # Evita derrubar o coletor por erro pontual de um contêiner
                    pass
            # pequeno sleep entre varreduras
            self._stop_evt.wait(self.poll_interval)

    def _copy_ids(self) -> List[str]:
        with self._lock:
            return list(self._container_ids)

    @staticmethod
    def _compute_metrics(container, stats: dict) -> Optional[dict]:
        """
        Calcula cpu_percent e memória (sem cache) a partir do payload do Docker.
        """
        try:
            cpu_percent = StatsCollector._calc_cpu_percent(stats)
            mem_usage = stats.get("memory_stats", {}).get("usage", 0) or 0
            cache_mem = stats.get("memory_stats", {}).get("stats", {}).get("cache", 0) or 0
            app_mem = max(mem_usage - cache_mem, 0)
            return {
                "id": container.id,
                "name": container.name,
                "cpu_percent": float(cpu_percent),
                "mem_app_mb": app_mem / (1024 * 1024),
                "raw_mem_usage": mem_usage,
                "cache_mem": cache_mem,
                "read_ts": stats.get("read", None),
            }
        except Exception:
            return None

    @staticmethod
    def _calc_cpu_percent(stats: dict) -> float:
        """
        Fórmula oficial (Docker) usando cpu_stats e precpu_stats.
        """
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})

        cpu_delta = float(cpu_stats.get("cpu_usage", {}).get("total_usage", 0)) - \
                    float(precpu_stats.get("cpu_usage", {}).get("total_usage", 0))
        system_delta = float(cpu_stats.get("system_cpu_usage", 0)) - \
                       float(precpu_stats.get("system_cpu_usage", 0))

        online_cpus = cpu_stats.get("online_cpus")
        if not online_cpus:
            online_cpus = len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", []) or []) or 1

        if system_delta > 0.0 and cpu_delta > 0.0:
            return (cpu_delta / system_delta) * online_cpus * 100.0
        return 0.0
