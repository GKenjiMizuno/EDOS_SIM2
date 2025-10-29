# edos_docker_simulation/config.py

# --- Configurações da Simulação ---
SIMULATION_DURATION_SECONDS = 180  # Total duration of the simulation
ATTACK_START_TIME_SECONDS = 30     # When the attack begins
ATTACK_DURATION_SECONDS = 60       # How long the attack lasts
PULSE_DURATION = 5


# --- Configurações do Docker ---
DOCKER_IMAGE_NAME = "edos_target_app:latest" # Matches the image you built
BASE_CONTAINER_NAME = "target_instance"    # Base name for your containers (e.g., target_instance_1)
DOCKER_NETWORK_NAME = "edos_network"       # Matches the network you created
STARTING_HOST_PORT = 8080 # Host port for the first container instance (8080 -> 80, 8081 -> 80, etc.)
# For app/simple_server.py to be configurable (optional, already defaults to 80 internally)
# CONTAINER_APP_PORT = 80

# --- Configurações do Autoescalonamento ---
MIN_INSTANCES = 1
MAX_INSTANCES = 3  # Start small for local testing on your VM
# For CPU % (real or simulated), use values between 0 and 100
CPU_THRESHOLD_SCALE_UP = 60.0   # % CPU average to trigger scale up
CPU_THRESHOLD_SCALE_DOWN = 25.0 # % CPU average to trigger scale down
SCALE_COOLDOWN_SECONDS = 20     # Cooldown period between scaling actions
MONITOR_INTERVAL_SECONDS = 5    # How often to check metrics and consider scaling

# --- Configurações de Tráfego ---
# For tcpreplay (if you get to it)
PCAP_FILE_NORMAL_TRAFFIC = "pcaps/normal_traffic.pcap" # You'll need to create/find this
TCPREPLAY_INTERFACE = "docker0" # Or the interface for your edos_network bridge (e.g., br-xxxx)

# HTTP Flood Attack Config
HTTP_ATTACK_TARGET_URL_BASE = "http://localhost" # The orchestrator will add the host port
HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER = 4 # RPS per attacking thread --- 5 foi um valor incial com bom resultado
HTTP_ATTACK_NUM_ATTACKERS = 4 # Number of concurrent attacking threads/processes  -- 2 foi um valor incial com bom resultado

# --- Configurações de Custo (Fictício) ---
COST_PER_INSTANCE_PER_HOUR = 0.02 # Example cost
# EGRESS_TRAFFIC_COST_PER_GB = 0.09 # Can add later if you measure egress

# --- Nomes de arquivos de Log ---
METRICS_LOG_FILE = "simulation_metrics.csv"

# ... outras configurações ...
HTTP_REQUEST_TIMEOUT_SECONDS = 10.0 # Timeout para cada requisição HTTP individual (em segundos)
APP_CONTAINER_PORT = 80

#Normal traffic metrics

HTTP_NORMAL_RPS_PER_CLIENT = 2
HTTP_NORMAL_NUM_CLIENTS = 5


# --- Configurações de Ataque EDoS (pulsado) ---
# Duração de um único pulso de tráfego intenso.
# Deve ser menor que MONITOR_INTERVAL_SECONDS para permitir que o CPU caia entre os pulsos.
# Ex: se MONITOR_INTERVAL_SECONDS = 5s, um pulso de 1s ou 2s é bom.
EDOS_PULSE_DURATION_SECONDS = 1.0

# RPS (Requests Per Second) por atacante durante o período de pulso intenso.
# Calibre este valor para levar o CPU acima de CPU_THRESHOLD_SCALE_UP durante o pulso.
EDOS_PULSE_RPS_PER_ATTACKER = 10 # Valor inicial, ajuste conforme o teste

# Número de atacantes durante o período de pulso intenso.
EDOS_PULSE_NUM_ATTACKERS = 5 # Valor inicial, ajuste conforme o teste

# RPS por atacante no período "idle" (entre os pulsos ou fora do ataque).
# Este valor deve ser baixo (preferencialmente 0) para permitir que o CPU caia.
EDOS_IDLE_RPS_PER_ATTACKER = 0.0

# Número de atacantes no período "idle" (pode ser 0).
EDOS_IDLE_NUM_ATTACKERS = 0 # Valor inicial, ajuste conforme o teste (0 é geralmente bom)

# Controla a duração do ataque para a fase de saturação (para atingir MAX_INSTANCES).
# Durante esta fase, o tráfego será constante (ou uma mistura dos pulsos e idle) para garantir o scale-up inicial.
# Após este tempo, a estratégia de pulsos pode ser mais rígida para manter o custo.
# Pode ser configurado como 0 se você quiser que os pulsos iniciem imediatamente.
EDOS_SATURATION_PHASE_DURATION_SECONDS = 60

#SIMPLE SERVER ATTACK PARAMETERS

ATTACK_WORK_UNITS = 2000000
ATTACK_SLEEP = 0.02

#SIMPLE SERVER NORMAL TRAFFIC PARAMETERS

NORMAL_WORK_UNITS = 10
NORMAL_SLEEP =0.0
