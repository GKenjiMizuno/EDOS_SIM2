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


def start_http_flood(target_host_port_pairs, duration_seconds):
    """
    Starts an HTTP flood attack against one or more target host:port pairs.
    target_host_port_pairs: A list of (host, port) tuples or a list of full URLs.
                            Example: [("localhost", 8080), ("localhost", 8081)]
                            Or: ["http://localhost:8080", "http://localhost:8081"]
    duration_seconds: How long the flood should last.
    """
    global attack_active, threads
    
    if not target_host_port_pairs:
        print("[Injector] No targets specified. Stopping flood.")
        return

    # Limpar threads de uma execução anterior, se houver
    if threads:
        print("[Injector] Warning: Previous threads found. Attempting to join them (should not happen if stop_http_flood was called).")
        attack_active = False # Garantir que threads antigos parem
        for t in threads:
            if t.is_alive():
                t.join(timeout=1.0) # Dar um pequeno timeout para threads antigos finalizarem
        threads = []


    attack_active = True
    threads = [] # Reiniciar a lista de threads

    num_attackers_per_target = config.HTTP_ATTACK_NUM_ATTACKERS
    rps_per_attacker = config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER
    
    total_rps_configured = 0

    print(f"[Injector] Starting HTTP flood for {duration_seconds} seconds.")
    print(f"[Injector] Configuration: Attackers per target = {num_attackers_per_target}, RPS per attacker = {rps_per_attacker}")

    for target_spec in target_host_port_pairs:
        target_url = ""
        if isinstance(target_spec, tuple) and len(target_spec) == 2:
            host, port = target_spec
            # Construir a URL baseada na configuração, assumindo HTTP por enquanto
            target_url = f"{config.HTTP_ATTACK_TARGET_URL_BASE}:{port}"
        elif isinstance(target_spec, str):
            target_url = target_spec # Assume a URL completa foi passada
        else:
            print(f"[Injector] Invalid target specification: {target_spec}. Skipping.")
            continue

        print(f"[Injector] Targeting URL: {target_url}")
        for i in range(num_attackers_per_target):
            thread = threading.Thread(target=http_request_worker, args=(target_url, rps_per_attacker), daemon=True)
            threads.append(thread)
            thread.start()
            total_rps_configured += rps_per_attacker
            
    print(f"[Injector] All {len(threads)} attacker threads started. Total configured RPS: {total_rps_configured:.2f}")

    if duration_seconds > 0:
        time.sleep(duration_seconds)
        print(f"[Injector] Flood duration ({duration_seconds}s) elapsed.")
        stop_http_flood()
    # Se duration_seconds <= 0, o flood continuará até stop_http_flood() ser chamado externamente.

def stop_http_flood():
    """
    Stops all active HTTP flood worker threads.
    """
    global attack_active, threads
    if not attack_active and not threads:
        print("[Injector] HTTP flood already stopped or not started.")
        return

    print("[Injector] Stopping HTTP flood...")
    attack_active = False
    
    # Aguardar os threads finalizarem
    for t in threads:
        if t.is_alive():
            t.join(timeout=5.0) # Timeout para cada thread finalizar
            if t.is_alive():
                print(f"[Injector] Warning: Thread {t.ident} did not stop in time.")
    
    threads = [] # Limpar a lista de threads
    print("[Injector] All HTTP flood threads stopped.")


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
