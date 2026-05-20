import csv
import time
import threading
import os

import config

FIELDNAMES = [
    "ts_iso",
    "event",
    "thread_id",
    "thread_name",
    "num_attackers",
    "rps_per_worker",
    "planned_total_rps",
    "num_targets",
    "target_urls",
    "total_requests",
    "errors"
]

_lock = threading.Lock()

attack_start = config.ATTACK_START_TIME_SECONDS
attack_end = attack_start + config.PULSE_DURATION


def init_attack_summary_log():
    """
    Cria/reinicia o CSV no começo da simulação.
    """
    with _lock:
        with open(config.ATTACK_SUMMARY_LOG_FILE, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_attack_start(target_urls, rps_per_worker, num_attackers):
    """
    Registra o início de um flood HTTP.
    """
    num_targets = len(target_urls)
    planned_total_rps = rps_per_worker * num_attackers

    row = {
        "event": "attack_start",
        "num_attackers": num_attackers,
        "rps_per_worker": rps_per_worker,
        "planned_total_rps": planned_total_rps,
        "num_targets": num_targets,
        "target_urls": "|".join(target_urls),
        "total_requests": "",
        "errors": ""
    }

    _append_row(row)


def log_worker_stop(request_count, error_count, rps_per_worker, num_attackers):
    """
    Registra o resumo final de uma thread atacante.
    Deve ser chamado dentro do worker, quando ele termina.
    """
    row = {
        "event": "worker_stop",
        "num_attackers": "",
        "rps_per_worker": "",
        "planned_total_rps": "",
        "num_targets": "",
        "target_urls": "",
        "total_requests": request_count,
        "errors": error_count + ((rps_per_worker * num_attackers) - request_count)
    }

    _append_row(row)


def _append_row(row):
    """
    Escrita protegida por lock para evitar conflito entre várias threads.
    """
    with _lock:
        file_exists = os.path.exists(config.ATTACK_SUMMARY_LOG_FILE)

        with open(config.ATTACK_SUMMARY_LOG_FILE, "a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)

            if not file_exists:
                writer.writeheader()

            writer.writerow(row)