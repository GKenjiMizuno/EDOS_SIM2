# edos_docker_simulation/traffic_injector.py
import requests
import time
import threading
import random
import config # Para obter HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER, HTTP_ATTACK_NUM_ATTACKERS
import statistics
import csv
import normal_traffic_summary_logger
from concurrent.futures import ThreadPoolExecutor


# Variável global para controlar a execução dos threads de ataque
traffic_active = False
threads = []
rtt_measurements = []
rtt_measurements_total = []
rtt_lock = threading.Lock()

# Pool compartilhado que efetivamente envia as requisições (open-loop), no mesmo
# padrão do injetor de ataque (traffic_injectorV0.py): o ritmo de disparo não
# espera essa pool terminar, e os intervalos entre disparos são independentes
# uns dos outros (necessário para que os sorteios de Poisson façam sentido).
_send_pool = ThreadPoolExecutor(max_workers=config.HTTP_NORMAL_MAX_CONCURRENT_SENDS)


def _send_one_normal(session, target_url, counters, counters_lock):
    """
    Executa a requisição bloqueante de fato. Roda numa thread da _send_pool,
    desacoplada do laço de ritmo em normal_http_request_worker.
    """
    start_time = time.monotonic()
    try:
        session.get(target_url, timeout=2)  # Timeout de 2 segundos

        rtt = (time.monotonic() - start_time) * 1000  # em milissegundos
        with rtt_lock:
            rtt_measurements.append(rtt)
            rtt_measurements_total.append({
                "timestamp": time.time(),
                "rtt": rtt
            })
        with counters_lock:
            counters["ok"] += 1
    except requests.exceptions.RequestException:
        with counters_lock:
            counters["err"] += 1


def normal_http_request_worker(target_url, rps_per_worker):
    """
    Worker thread function. Dispara requisições para target_url no ritmo de rps_per_worker,
    sem esperar a resposta de uma requisição antes de agendar a próxima (open-loop), com
    intervalos entre disparos sorteados de uma distribuição exponencial (processo de
    Poisson de taxa rps_per_worker) em vez de um intervalo fixo — modela clientes
    independentes, como assumido em Sotelo Monge et al.
    """
    global traffic_active
    session = requests.Session() # Use session for potential connection pooling
    mean_interval = 1.0 / rps_per_worker if rps_per_worker > 0 else 1.0
    worker_start_time = time.monotonic()

    print(f"  [Normal_Injector Worker {threading.get_ident()}] Started. Target: {target_url}, RPS: {rps_per_worker:.2f}, Mean interval: {mean_interval:.4f}s (Poisson)")

    counters = {"ok": 0, "err": 0}
    counters_lock = threading.Lock()
    pending_futures = []

    while traffic_active:
        try:
            future = _send_pool.submit(_send_one_normal, session, target_url, counters, counters_lock)
        except RuntimeError:
            # _send_pool já foi finalizada (ex.: encerramento do interpretador) — encerra o worker.
            break
        pending_futures.append(future)
        # Descartar futures já concluídas para não acumular memória em execuções longas.
        pending_futures = [f for f in pending_futures if not f.done()]

        # Próximo intervalo sorteado independentemente (memoryless), não corrigido pelo
        # tempo de despacho — o despacho na _send_pool é rápido o bastante para não
        # distorcer a taxa alvo.
        sleep_duration = random.expovariate(rps_per_worker) if rps_per_worker > 0 else 1.0
        time.sleep(sleep_duration)

    # Esperar as requisições ainda em voo terminarem antes de contabilizar o resumo final.
    for f in pending_futures:
        try:
            f.result(timeout=3)  # timeout da requisição (2s) + margem de segurança
        except Exception:
            pass

    with counters_lock:
        request_count, error_count = counters["ok"], counters["err"]

    print(f"  [Normal_Injector Worker {threading.get_ident()}] Stopped. Total requests: {request_count}, Errors: {error_count}")

    normal_traffic_summary_logger.log_worker_stop(
        request_count=request_count,
        error_count=error_count,
        worker_start_time=worker_start_time,
        rps_per_worker=rps_per_worker,
    )

def save_rtt_log(filename=None):
    if filename is None:
        filename = config.RTT_LOG_FILE
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "rtt"])

        for entry in rtt_measurements_total:
            writer.writerow([entry["timestamp"], entry["rtt"]])



# edos_docker_simulation/traffic_injector.py

# ... (mantenha os imports e a definição de http_request_worker como está) ...

# Variável global para controlar a execução dos threads de ataque
traffic_active = False
# renomeando para 'attacker_threads' para clareza e consistência
# Comente ou remova a linha 'threads = []' se ela existir e você não a estiver usando
client_threads = [] 


def get_average_rtt_ms():
    global rtt_measurements
    with rtt_lock:
        if not rtt_measurements:
            return 0.0
        avg_rtt = statistics.mean(rtt_measurements)
        rtt_measurements = []
        return avg_rtt



def start_http_traffic(target_urls, rps_per_worker_override, num_clients_override):
    """
    Starts an HTTP flood attack against specified target URLs.
    This function starts worker threads and returns immediately (non-blocking).
    The attack continues until stop_http_flood() is called.

    Args:
        target_urls (list): A list of full URLs to target (e.g., ["http://localhost:8080"]).
        rps_per_worker_override (float): The Requests Per Second (RPS) each worker thread should aim for.
        num_attackers_override (int): The total number of attacker threads to launch.
    """
    global traffic_active, client_threads
    
    if not target_urls:
        print("[Normal_Injector] No target URLs provided. Attack not started.")
        return
    if traffic_active:
        print("[Normal_Injector] Normal traffic already in progress. Call stop_http_traffic() first.")
        return

    traffic_active = True
    # Limpar threads antigas é importante se o orchestrator não garante que stop_http_flood completou totalmente
    if client_threads:
        print(f"[Normal_Injector] Clearing {len(client_threads)} existing attacker threads before starting new ones.")
    client_threads.clear()

    num_targets = len(target_urls)

    print(f"[Normal_Injector] Starting HTTP flood with {num_clients_override} attackers, ~{rps_per_worker_override * num_clients_override} RPS total, across {num_targets} targets: {', '.join(target_urls)}")

    normal_traffic_summary_logger.log_traffic_start(
        target_urls=target_urls,
        rps_per_worker=rps_per_worker_override,
        num_clients=num_clients_override,
    )

    for i in range(num_clients_override):
        # Distribuição Round Robin dos workers pelas URLs de destino
        if num_targets == 0:
            print("[Normal_Injector] No targets available for worker assignment. Breaking loop.")
            break
        target_url_for_this_worker = target_urls[i % num_targets] + f"?work={config.NORMAL_WORK_UNITS}&sleep={config.NORMAL_SLEEP}"
        
        thread = threading.Thread(
            target=normal_http_request_worker,
            args=(target_url_for_this_worker, rps_per_worker_override), # Cada thread pode ter uma URL diferente
            daemon=True,
            name=f"InjectorWorker-{i+1}"
        )
        client_threads.append(thread)
        thread.start()
        
    print(f"[Normal_Injector] All {len(client_threads)} attacker threads launched.")

def stop_http_traffic():
    """
    Non-blocking stop.
    Signals workers to stop but does NOT block the orchestrator loop.
    """
    global traffic_active, client_threads

    if not traffic_active and not client_threads:
        print("[Normal_Injector] HTTP normal traffic already stopped.")
        return

    print("[Normal_Injector] Signaling workers to stop...")
    traffic_active = False

    threads_to_join = list(client_threads)
    client_threads.clear()

    # JOIN CURTO E NÃO BLOQUEANTE
    for thread_obj in threads_to_join:
        if thread_obj.is_alive():
            thread_obj.join(timeout=0.1)  # máximo 100ms

    print("[Normal_Injector] Stop signal sent (non-blocking).")

# ... (mantenha o bloco if __name__ == "__main__": inalterado, ele serve para teste do módulo) ...

# --- Self-test section (optional, for direct testing of this module) ---
if __name__ == "__main__":
    import docker_manager # Para iniciar um servidor de teste

    print("--- Running normal_traffic.py self-test ---")

    # 1. Iniciar uma instância de teste do simple_server.py usando docker_manager
    #    Precisamos garantir que a imagem exista e a rede também.
    if not docker_manager.build_docker_image():
        print("[Self-Test] Failed to build Docker image. Aborting self-test.")
        exit(1)
    if not docker_manager.ensure_docker_network():
        print("[Self-Test] Failed to ensure Docker network. Aborting self-test.")
        exit(1)

    docker_manager.cleanup_all_simulation_instances() # Limpar antes do teste
    
    test_instance_id = 99 # Usar um ID alto para não colidir com simulações normais
    test_container = docker_manager.start_instance(test_instance_id)
    if not test_container:
        print("[Self-Test] Failed to start test container. Aborting self-test.")
        exit(1)
    
    test_container.reload() # Carregar atributos
    test_host_port = None
    try:
        # Obter a porta mapeada do host para o contêiner de teste
        port_mappings = test_container.attrs['NetworkSettings']['Ports'].get('80/tcp')
        if port_mappings and isinstance(port_mappings, list) and len(port_mappings) > 0:
            test_host_port = int(port_mappings[0].get('HostPort'))
            print(f"[Self-Test] Test container '{test_container.name}' running on host port {test_host_port}")
        else:
            raise ValueError("Could not determine host port for test container.")

        # Construir a URL de teste completa
        test_target_url = f"http://localhost:{test_host_port}" # Ou config.HTTP_ATTACK_TARGET_URL_BASE se for localhost

        # 2. Configurar o tráfego de teste (valores menores para não sobrecarregar)
        print("\n[Self-Test] Starting test HTTP flood...")
        config.HTTP_NORMAL_NUM_CLIENTS = 2 # Sobrescrever para o teste
        config.HTTP_NORMAL_RPS_PER_CLIENT = 5 # Sobrescrever para o teste
        
        # O self-test pode usar uma URL completa diretamente ou a tupla (host, port)
        # start_http_flood([("localhost", test_host_port)], duration_seconds=10)
        start_http_traffic([test_target_url], duration_seconds=10) # Inicia por 10s e para automaticamente

        # Se quiséssemos testar start/stop manualmente:
        # start_http_flood([test_target_url], duration_seconds=0) # Inicia e continua
        # print("[Self-Test] Flood started. Waiting 10 seconds before manual stop...")
        # time.sleep(10)
        # stop_http_flood()

        print("[Self-Test] Test HTTP flood completed.")

    except Exception as e:
        print(f"[Self-Test] An error occurred during self-test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 3. Parar e remover a instância de teste
        print("\n[Self-Test] Cleaning up test container...")
        if test_container:
            docker_manager.stop_instance(test_container.name)
        print("[Self-Test] Cleanup complete.")

    print("--- normal_traffic.py self-test complete ---")
