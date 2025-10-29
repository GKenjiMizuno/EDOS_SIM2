import time
import csv
import docker # Certifique-se de que 'docker' SDK está instalado (pip install docker)

# Importar seus outros módulos (assumindo que estão no mesmo diretório ou no PYTHONPATH)
import config
import docker_manager
import autoscaler_logic
import traffic_injector
import cost_calculator # Se você tem um módulo separado para isso
from stats_collector import StatsCollector
import normal_traffic

# --- Função de Logging para CSV (pode estar aqui ou em um módulo utilitário) ---
def log_metrics_to_csv(elapsed_time, num_instances, avg_cpu, mem_usage, decision, active_names, label):
    try:
        with open(config.METRICS_LOG_FILE, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['elapsed_time_s', 'num_instances', 'average_cpu_percent', 'mem_usage', 'decision', 'active_containers_names', 'label'])
            writer.writerow({
                'elapsed_time_s': round(elapsed_time, 2),
                'num_instances': num_instances,
                'average_cpu_percent': round(avg_cpu, 2),
                'mem_usage': round(mem_usage,2),
                'decision': decision,
                'active_containers_names': ','.join(active_names) if active_names else '',
                'label': label,
            })
    except Exception as e:
        print(f"[Orchestrator] Error logging metrics to CSV: {e}")

# --- Função Principal da Simulação ---
def main():

    global stats_collector

    print("[Orchestrator] Initializing simulation environment...")
    
    # --- CORREÇÃO AQUI: Instanciar a classe Autoscaler ---
    autoscaler = autoscaler_logic.Autoscaler() # Cria uma instância da classe Autoscaler

    if not docker_manager.build_docker_image(): # Usando diretamente se são funções
        print("[Orchestrator] CRITICAL: Failed to build Docker image. Aborting.")
        return
    if not docker_manager.ensure_docker_network():
        print("[Orchestrator] CRITICAL: Failed to ensure Docker network. Aborting.")
        return

    print("[Orchestrator] Cleaning up any pre-existing simulation instances...")
    docker_manager.cleanup_all_simulation_instances()

    active_containers = [] # Lista de objetos container do Docker SDK
    next_instance_numeric_id = 1
    print(f"[Orchestrator] Starting initial {config.MIN_INSTANCES} instance(s)...")
    for _ in range(config.MIN_INSTANCES):
        # Assumindo que start_instance retorna o objeto container ou None
        container = docker_manager.start_instance(next_instance_numeric_id)
        if container:
            active_containers.append(container)
            next_instance_numeric_id += 1
        else:
            print(f"[Orchestrator] CRITICAL: Failed to start initial instance {next_instance_numeric_id}. Aborting.")
            docker_manager.cleanup_all_simulation_instances() # Limpar o que foi iniciado
            return
    
    # ... após preencher active_containers ...
    stats_collector = StatsCollector(client=docker_manager.client,
                        poll_interval=getattr(config, "DOCKER_STATS_POLL_INTERVAL_SECONDS", 1.0))
    stats_collector.start()
    stats_collector.update_containers(active_containers)

            
    if not active_containers and config.MIN_INSTANCES > 0:
        print("[Orchestrator] CRITICAL: No initial instances were started. Aborting.")
        return

    # --- CORREÇÃO AQUI: Chamar o método na instância 'autoscaler' ---
    autoscaler.set_initial_instances(len(active_containers)) # Agora chama na instância
    print(f"[Orchestrator] {len(active_containers)} initial instance(s) running.")

    start_time = time.time()
    simulation_duration = config.SIMULATION_DURATION_SECONDS
    
    instance_intervals_for_cost = [] # Para cálculo de custo

    # --- Variáveis para controle do ataque EDoS ---
    # tracked_attack_state: 'idle', 'saturating', 'pulsing', 'idle_between_pulses'
    tracked_attack_state = 'idle' 
    last_pulse_end_time = 0.0 # Hora que o último pulso terminou, para gerenciar o próximo

    # --- Inicialização da flag de ataque do injetor ---
    # Garante que o injetor comece limpo. (traffic_injector.py foi alterado para usar attacker_threads)
    traffic_injector.attack_active = False 
    traffic_injector.attacker_threads = [] 

    # --- Variáveis para a lógica de reinício do injetor ---
    previous_num_instances_for_injector_logic = len(active_containers) # Estado para lógica de reinício do injetor
    attack_has_started = False  # Se o injetor foi iniciado pelo menos uma vez
    normal_traffic_has_started = False

    # Configurar arquivo de log CSV no início
    try:
        with open(config.METRICS_LOG_FILE, 'w', newline='') as csvfile:
            fieldnames = ['elapsed_time_s', 'num_instances', 'average_cpu_percent', 'mem_usage',
                  'decision', 'active_containers_names', 'label']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        print(f"[Orchestrator] Metrics will be logged to: {config.METRICS_LOG_FILE}")
    except Exception as e_csv_init:
        print(f"[Orchestrator] CRITICAL: Failed to initialize metrics log file {config.METRICS_LOG_FILE}. Error: {e_csv_init}. Aborting.")
        docker_manager.cleanup_all_simulation_instances()
        return

    print(f"[Orchestrator] Starting simulation main loop for {simulation_duration} seconds.")
    print(f"[Orchestrator] Monitoring interval: {config.MONITOR_INTERVAL_SECONDS}s. Cooldown: {config.SCALE_COOLDOWN_SECONDS}s.")
    print(f"[Orchestrator] CPU Thresholds: Scale Up > {config.CPU_THRESHOLD_SCALE_UP}%, Scale Down < {config.CPU_THRESHOLD_SCALE_DOWN}%")
    if config.ATTACK_DURATION_SECONDS > 0:
        print(f"[Orchestrator] Traffic injection scheduled: Start at {config.ATTACK_START_TIME_SECONDS}s, Duration {config.ATTACK_DURATION_SECONDS}s.")
    else:
        print("[Orchestrator] No traffic injection scheduled (ATTACK_DURATION_SECONDS is 0 or less).")

    attack_start_time = config.ATTACK_START_TIME_SECONDS
    attack_end = attack_start_time + config.SCALE_COOLDOWN_SECONDS

    main_loop_iteration = 0
    while (time.time() - start_time) < simulation_duration:
        current_loop_start_time = time.time() # Para calcular o tempo de sleep
        time.sleep(0.01)
        elapsed_time_seconds = current_loop_start_time - start_time
        main_loop_iteration += 1
        label = 'normal'
        print(f"\n--- Iteration {main_loop_iteration} | Time: {elapsed_time_seconds:.1f}s / {simulation_duration}s ---")

        # 1. Validar e Coletar Métricas das Instâncias Ativas

        stats_collector.update_containers(active_containers)

        current_num_instances_actual = len(active_containers)
        avg_cpu, avg_mem_app_mb, current_active_container_names = stats_collector.get_averages()

        if current_num_instances_actual == 0 and config.MIN_INSTANCES > 0 and elapsed_time_seconds > config.MONITOR_INTERVAL_SECONDS:
                print("[Orchestrator] CRITICAL WARNING: No active instances running, but MIN_INSTANCES > 0.")
        print(f"[Orchestrator] Metrics: {current_num_instances_actual} active instance(s), "
            f"Avg CPU: {avg_cpu:.2f}%, Avg App MEM: {avg_mem_app_mb:.2f} MB")


        # 2. Decidir sobre o escalonamento
        # --- CORREÇÃO AQUI: ChamaFr o método na instância 'autoscaler' ---
        scaling_decision = autoscaler.decide_scaling(avg_cpu, current_num_instances_actual)

        # 3. Executar ações de escalonamento (atualiza 'active_containers' e 'next_instance_numeric_id')
        if scaling_decision == "SCALE_UP":
            if current_num_instances_actual < config.MAX_INSTANCES:
                print(f"[Orchestrator] Action: Scaling UP from {current_num_instances_actual} instance(s). Attempting to start instance {next_instance_numeric_id}.")
                new_container = docker_manager.start_instance(next_instance_numeric_id)
                if new_container:
                    active_containers.append(new_container)
                    stats_collector.update_containers(active_containers)
                    next_instance_numeric_id += 1
                    print(f"[Orchestrator] Successfully started {new_container.name}. Now {len(active_containers)} instance(s).")
                else:
                    print(f"[Orchestrator] Failed to start new instance for SCALE_UP.")
            else:
                print(f"[Orchestrator] SCALE_UP requested, but already at MAX_INSTANCES ({config.MAX_INSTANCES}). No action.")
        elif scaling_decision == "SCALE_DOWN":
            if current_num_instances_actual > config.MIN_INSTANCES:
                # Simples: para o último da lista. Poderia ser mais sofisticado.
                container_to_stop = active_containers.pop()
                stats_collector.update_containers(active_containers)
                print(f"[Orchestrator] Action: Scaling DOWN from {current_num_instances_actual} instance(s). Stopping {container_to_stop.name}.")
                if docker_manager.stop_instance(container_to_stop.name): # stop_instance deve retornar True/False
                    print(f"[Orchestrator] Successfully stopped {container_to_stop.name}. Now {len(active_containers)} instance(s).")
                else:
                    print(f"[Orchestrator] Failed to stop {container_to_stop.name}. Adding back to active list (caution).")
                    active_containers.append(container_to_stop) # Adicionar de volta se a parada falhou
            else:
                 print(f"[Orchestrator] SCALE_DOWN requested, but already at MIN_INSTANCES ({config.MIN_INSTANCES}). No action.")
        
        # Número de instâncias após scaling para esta iteração
        num_instances_after_scaling = len(active_containers)
        autoscaler.record_scale_action(num_instances_after_scaling) # Atualizar o autoscaler

        # 4. Gerenciar o injetor de tráfego (COM LÓGICA DE REINÍCIO E LOGS)
        target_urls_for_injector = []
        if active_containers: # Somente tente obter URLs se houver contêineres ativos
            for c_obj in active_containers:
                try:
                    c_obj.reload() # Essencial para obter os atributos mais recentes, incluindo portas
                    port_mappings = c_obj.attrs.get('NetworkSettings', {}).get('Ports', {}).get(f'{config.APP_CONTAINER_PORT}/tcp')
                    if port_mappings and isinstance(port_mappings, list) and len(port_mappings) > 0:
                        host_port = port_mappings[0].get('HostPort')
                        if host_port:
                            target_urls_for_injector.append(f"http://localhost:{host_port}") # Ou config.TARGET_HOST
                        else:
                            print(f"[Orchestrator] Warning: HostPort not found for {c_obj.name} in '{config.APP_CONTAINER_PORT}/tcp' mapping: {port_mappings[0]}")
                    else:
                        print(f"[Orchestrator] Warning: No '{config.APP_CONTAINER_PORT}/tcp' mapping found or empty for {c_obj.name}. Ports: {c_obj.attrs.get('NetworkSettings', {}).get('Ports', {})}")
                except Exception as e_port:
                    print(f"[Orchestrator] Error reloading or getting port for container {c_obj.name} for traffic injection: {e_port}")

        print(f"[DEBUG Orchestrator] Iteration Start. Instances Before Injector Logic: {num_instances_after_scaling}, Prev Injector Logic Instances: {previous_num_instances_for_injector_logic}, Attack Started Flag: {attack_has_started}, Normal Traffic Started Flag: {normal_traffic_has_started}")
        print(f"[DEBUG Orchestrator] URLs derived for injector (if active): {target_urls_for_injector}")

        if config.ATTACK_DURATION_SECONDS == 0:
                print(f"[Orchestrator] Starting/Restarting Normal Traffic. Target URLs for this call: {target_urls_for_injector}")
                normal_traffic.start_http_traffic(
                        target_urls_for_injector,
                        config.HTTP_NORMAL_RPS_PER_CLIENT,
                        config.HTTP_NORMAL_NUM_CLIENTS
                    )
                normal_traffic_has_started = True

        if config.ATTACK_DURATION_SECONDS > 0:
            label = 'normal'
            if current_num_instances_actual < config.MAX_INSTANCES:
                is_max_instance = False
            
            else:
                is_max_instance = True


            should_attack_be_active_now = (attack_start_time <= elapsed_time_seconds < attack_end)
            print(f"[DEBUG Orchestrator] Should attack be active now? {should_attack_be_active_now}")

            print(f"[DEBUG Orchestrator] {attack_start_time} {attack_end}")

            needs_injector_start_or_restart = False

            #------------------COMEÇAR AQUI A LOGICA DE TRAFEGO NORMAL --------------------------

            if not should_attack_be_active_now:
                print(f"[Orchestrator] Starting/Restarting Normal Traffic. Target URLs for this call: {target_urls_for_injector}")
                normal_traffic.start_http_traffic(
                        target_urls_for_injector,
                        config.HTTP_NORMAL_RPS_PER_CLIENT,
                        config.HTTP_NORMAL_NUM_CLIENTS
                    )
                normal_traffic_has_started = True

            
            if should_attack_be_active_now:
                print(f"[Orchestrator] Stopping Normal traffic...")
                normal_traffic.stop_http_traffic()
                normal_traffic_has_started = False




            #Se não esta em instancias maximas
            if should_attack_be_active_now and not is_max_instance:
                attack_start_time = attack_start_time + config.SCALE_COOLDOWN_SECONDS
                attack_end = attack_end + config.SCALE_COOLDOWN_SECONDS
                if not attack_has_started: # Se o ataque deve começar e ainda não começou
                    needs_injector_start_or_restart = True
                    print("[DEBUG Orchestrator] Condition: Needs to START attack (was not started and in attack window).")
                # Se o ataque já começou E o número de instâncias mudou E temos alvos
                elif attack_has_started and previous_num_instances_for_injector_logic != num_instances_after_scaling and target_urls_for_injector:
                    needs_injector_start_or_restart = True
                    print(f"[DEBUG Orchestrator] Condition: Needs to RESTART attack (num instances changed from {previous_num_instances_for_injector_logic} to {num_instances_after_scaling} AND attack was active).")
            
            #Se esta em instância máxima
            if should_attack_be_active_now and is_max_instance:
                attack_start_time = attack_start_time + config.MONITOR_INTERVAL_SECONDS
                attack_end = attack_end + config.MONITOR_INTERVAL_SECONDS

                if not attack_has_started: # Se o ataque deve começar e ainda não começou
                    needs_injector_start_or_restart = True
                    print("[DEBUG Orchestrator] Condition: Needs to START attack (was not started and in attack window).")
                # Se o ataque já começou E o número de instâncias mudou E temos alvos
                elif attack_has_started and previous_num_instances_for_injector_logic != num_instances_after_scaling and target_urls_for_injector:
                    needs_injector_start_or_restart = True
                    print(f"[DEBUG Orchestrator] Condition: Needs to RESTART attack (num instances changed from {previous_num_instances_for_injector_logic} to {num_instances_after_scaling} AND attack was active).")
            


            if needs_injector_start_or_restart:
                if attack_has_started: # Se já estava rodando, pare primeiro
                    print("[Orchestrator] Attack active and restart needed. Stopping current traffic injector...")
                    traffic_injector.stop_http_flood()
                    print("[DEBUG Orchestrator] Called stop_http_flood. Sleeping for 1s...")
                    time.sleep(1) # Pausa para as threads do injetor pararem
                    print("[DEBUG Orchestrator] Resuming after sleep.")
                
                if target_urls_for_injector: # Somente inicie/reinicie se houver alvos
                    print(f"[Orchestrator] Starting/Restarting HTTP flood. Target URLs for this call: {target_urls_for_injector}")
                    traffic_injector.start_http_flood(
                        target_urls_for_injector,
                        config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER,
                        config.HTTP_ATTACK_NUM_ATTACKERS
                    )
                    label = 'attack'
                    attack_has_started = True # Marcar que o ataque (re)começou
                    print(f"[DEBUG Orchestrator] attack_has_started flag set to TRUE.")
                else:
                    print("[Orchestrator] Attack start/restart requested, but no valid target URLs. Injector not started/restarted.")
                    if attack_has_started: # Se estava ativo mas agora não tem alvos
                        print("[DEBUG Orchestrator] Attack was active but now no targets. Signaling stop and setting flag to False.")
                        traffic_injector.stop_http_flood() # Parar se estava ativo e agora não tem alvos
                        attack_has_started = False
            elif not should_attack_be_active_now and attack_has_started: # Se o período de ataque terminou
                print("[Orchestrator] Attack duration ended or outside schedule. Stopping HTTP flood.")
                traffic_injector.stop_http_flood()
                attack_has_started = False
                print("[DEBUG Orchestrator] attack_has_started flag set to FALSE (attack period ended).")

        # Atualizar o número de instâncias para a lógica do injetor na PRÓXIMA iteração
        previous_num_instances_for_injector_logic = num_instances_after_scaling
        print(f"[DEBUG Orchestrator] End of Iteration. previous_num_instances_for_injector_logic updated to: {previous_num_instances_for_injector_logic}")

        # 5. Registrar métricas no CSV
        log_metrics_to_csv(elapsed_time_seconds, num_instances_after_scaling, avg_cpu, avg_mem_app_mb, scaling_decision, current_active_container_names,label)
        
        # 6. Acumular dados para cálculo de custo
        instance_intervals_for_cost.append((num_instances_after_scaling, config.MONITOR_INTERVAL_SECONDS))
        
        # 7. Aguardar próximo ciclo
        # Calcular tempo real da iteração e dormir apenas o necessário
        current_loop_duration = time.time() - current_loop_start_time
        time_to_sleep = config.MONITOR_INTERVAL_SECONDS - current_loop_duration
        if time_to_sleep > 0:
            # print(f"[DEBUG Orchestrator] Sleeping for {time_to_sleep:.2f}s")
            time.sleep(time_to_sleep)
        else:
            print(f"[Orchestrator] Warning: Loop iteration ({current_loop_duration:.2f}s) took longer than MONITOR_INTERVAL_SECONDS ({config.MONITOR_INTERVAL_SECONDS}s). Not sleeping.")

    # --- Fim do loop de simulação ---
    print("\n[Orchestrator] Simulation duration reached.")

    if traffic_injector.attack_active: # Verifica o estado real no módulo traffic_injector
        print("[Orchestrator] Stopping any active traffic injection at end of simulation...")
        traffic_injector.stop_http_flood()

    print("[Orchestrator] Cleaning up all simulation instances...")
    docker_manager.cleanup_all_simulation_instances()

    try:
        print("[Stats_Collector] Stopping stats collector thread...")
        stats_collector.stop()
    except Exception:
        pass

    if hasattr(cost_calculator, 'calculate_total_cost_from_intervals'):
        total_simulation_cost = cost_calculator.calculate_total_cost_from_intervals(instance_intervals_for_cost)
        print(f"[Orchestrator] Simulation Complete. Total Fictional Cost: ${total_simulation_cost:.4f}")
    else:
        print("[Orchestrator] Simulation Complete. Cost calculation module/function not found.")
    print(f"[Orchestrator] Metrics logged in: {config.METRICS_LOG_FILE}")

# --- Bloco de Execução Principal ---
if __name__ == "__main__":
    stats_collector = None
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Orchestrator] Simulation interrupted by user (Ctrl+C). Attempting cleanup...")
        if hasattr(traffic_injector, 'attack_active') and traffic_injector.attack_active:
            print("[Orchestrator] Stopping traffic injector due to interruption...")
            traffic_injector.stop_http_flood()
            normal_traffic.stop_http_traffic()

        # pare a thread de stats se existir
        try:
            if stats_collector is not None:
                print("[Stats_Collector] Stopping stats collector thread...")
                stats_collector.stop()
        except Exception:
            pass

        if hasattr(docker_manager, 'cleanup_all_simulation_instances'):
            print("[Orchestrator] Cleaning up Docker instances due to interruption...")
            docker_manager.cleanup_all_simulation_instances()

        print("[Orchestrator] Cleanup attempt complete due to interruption.")
    except Exception as e_global:
        print(f"[Orchestrator] An UNEXPECTED GLOBAL ERROR occurred: {e_global}")
        import traceback
        traceback.print_exc()
        print("[Orchestrator] Attempting cleanup after unexpected global error...")
        if hasattr(traffic_injector, 'attack_active') and traffic_injector.attack_active:
            print("[Orchestrator] Stopping traffic injector due to error...")
            traffic_injector.stop_http_flood()
            normal_traffic.stop_http_traffic()
        
        # pare a thread de stats se existir
        try:
            if stats_collector is not None:
                print("[Stats_Collector] Stopping stats collector thread...")
                stats_collector.stop()
        except Exception:
            pass

        if hasattr(docker_manager, 'cleanup_all_simulation_instances'):
            print("[Orchestrator] Cleaning up Docker instances due to error...")
            docker_manager.cleanup_all_simulation_instances()
        print("[Orchestrator] Cleanup attempt complete after error.")
