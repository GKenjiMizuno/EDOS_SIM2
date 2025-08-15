# edos_docker_simulation/traffic_injector.py
import requests
import time
import threading
import config # Para obter HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER, HTTP_ATTACK_NUM_ATTACKERS

# Variável global para controlar a execução dos threads de ataque
attack_active = False
threads = []

def http_request_worker(target_url, rps_per_worker):
    """
    Worker thread function. Sends requests to target_url at a specified RPS.
    """
    global attack_active
    session = requests.Session() # Use session for potential connection pooling
    sleep_interval = 1.0 / rps_per_worker if rps_per_worker > 0 else 1.0

    print(f"  [Injector Worker {threading.get_ident()}] Started. Target: {target_url}, RPS: {rps_per_worker:.2f}, Interval: {sleep_interval:.4f}s")
    
    request_count = 0
    error_count = 0

    while attack_active:
        start_time = time.monotonic()
        try:
            response = session.get(target_url, timeout=2) # Timeout de 2 segundos
            # Você pode verificar response.status_code se precisar
            # if response.status_code == 200:
            #     pass
            request_count +=1
        except requests.exceptions.RequestException as e:
            # print(f"  [Injector Worker {threading.get_ident()}] Request error: {e}")
            error_count += 1
        
        # Calcular o tempo gasto e ajustar o sono para manter o RPS
        time_taken = time.monotonic() - start_time
        sleep_duration = sleep_interval - time_taken
        if sleep_duration > 0:
            time.sleep(sleep_duration)
        # Se time_taken > sleep_interval, o worker está atrasado (não consegue manter o RPS)
        # Não há muito o que fazer aqui além de registrar ou ajustar o RPS se for um problema.

    print(f"  [Injector Worker {threading.get_ident()}] Stopped. Total requests: {request_count}, Errors: {error_count}")


# edos_docker_simulation/traffic_injector.py

# ... (mantenha os imports e a definição de http_request_worker como está) ...

# Variável global para controlar a execução dos threads de ataque
attack_active = False
# renomeando para 'attacker_threads' para clareza e consistência
# Comente ou remova a linha 'threads = []' se ela existir e você não a estiver usando
attacker_threads = [] 


def start_http_flood(target_urls, rps_per_worker_override, num_attackers_override):
    """
    Starts an HTTP flood attack against specified target URLs.
    This function starts worker threads and returns immediately (non-blocking).
    The attack continues until stop_http_flood() is called.

    Args:
        target_urls (list): A list of full URLs to target (e.g., ["http://localhost:8080"]).
        rps_per_worker_override (float): The Requests Per Second (RPS) each worker thread should aim for.
        num_attackers_override (int): The total number of attacker threads to launch.
    """
    global attack_active, attacker_threads
    
    if not target_urls:
        print("[Injector] No target URLs provided. Attack not started.")
        return
    if attack_active:
        print("[Injector] Attack already in progress. Call stop_http_flood() first.")
        return

    attack_active = True
    # Limpar threads antigas é importante se o orchestrator não garante que stop_http_flood completou totalmente
    if attacker_threads:
        print(f"[Injector] Clearing {len(attacker_threads)} existing attacker threads before starting new ones.")
    attacker_threads.clear()

    num_targets = len(target_urls)
    
    print(f"[Injector] Starting HTTP flood with {num_attackers_override} attackers, ~{rps_per_worker_override * num_attackers_override} RPS total, across {num_targets} targets: {', '.join(target_urls)}")

    for i in range(num_attackers_override):
        # Distribuição Round Robin dos workers pelas URLs de destino
        if num_targets == 0:
            print("[Injector] No targets available for worker assignment. Breaking loop.")
            break
        target_url_for_this_worker = target_urls[i % num_targets]
        
        thread = threading.Thread(
            target=http_request_worker,
            args=(target_url_for_this_worker, rps_per_worker_override), # Cada thread pode ter uma URL diferente
            daemon=True,
            name=f"InjectorWorker-{i+1}"
        )
        attacker_threads.append(thread)
        thread.start()
        
    print(f"[Injector] All {len(attacker_threads)} attacker threads launched.")

# Esta é a versão revisada e mais robusta do stop_http_flood
def stop_http_flood():
    """
    Stops all active HTTP flood worker threads.
    Signals workers to stop and waits for them to terminate.
    """
    global attack_active, attacker_threads 

    if not attack_active and not attacker_threads:
        print("[Injector] HTTP flood already stopped or not started.")
        return

    print("[Injector] Signaling HTTP flood workers to stop...")
    attack_active = False # Sinaliza aos workers para terminarem seus loops

    # Fazer uma cópia da lista de threads para dar join.
    threads_to_join = list(attacker_threads) 

    if not threads_to_join:
        print("[Injector] No threads were in the attacker_threads list to join.")
        attacker_threads.clear() 
        return

    print(f"[Injector] Attempting to stop and join {len(threads_to_join)} HTTP flood worker(s)...")

    # Limpar a lista global de threads ANTES de dar join.
    attacker_threads.clear()
    
    # Aguardar cada thread finalizar (join)
    for i, thread_obj in enumerate(threads_to_join):
        thread_name = thread_obj.name if hasattr(thread_obj, 'name') else f"Thread-{thread_obj.ident}"

        if thread_obj.is_alive():
            # O timeout do join deve ser um pouco maior que o timeout da requisição HTTP,
            # para dar tempo à thread de finalizar sua última requisição e o loop.
            join_timeout = (config.HTTP_REQUEST_TIMEOUT_SECONDS if hasattr(config, 'HTTP_REQUEST_TIMEOUT_SECONDS') else 2) + 2.0 
            thread_obj.join(timeout=join_timeout)

            if thread_obj.is_alive():
                print(f"[Injector] Warning: Worker thread {thread_name} did not terminate gracefully within {join_timeout}s timeout.")
            else:
                print(f"[Injector] Thread {thread_name} joined successfully.")
        else:
            print(f"[Injector] Thread {thread_name} was already not alive before join attempt.")

    print("[Injector] All HTTP flood workers have been processed for stopping.")


# ... (mantenha o bloco if __name__ == "__main__": inalterado, ele serve para teste do módulo) ...

# --- Self-test section (optional, for direct testing of this module) ---
if __name__ == "__main__":
    import docker_manager # Para iniciar um servidor de teste

    print("--- Running traffic_injector.py self-test ---")

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
        config.HTTP_ATTACK_NUM_ATTACKERS = 2 # Sobrescrever para o teste
        config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER = 5 # Sobrescrever para o teste
        
        # O self-test pode usar uma URL completa diretamente ou a tupla (host, port)
        # start_http_flood([("localhost", test_host_port)], duration_seconds=10)
        start_http_flood([test_target_url], duration_seconds=10) # Inicia por 10s e para automaticamente

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

    print("--- traffic_injector.py self-test complete ---")
