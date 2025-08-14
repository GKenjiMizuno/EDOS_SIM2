# edos_docker_simulation/config.py

# --- Configurações da Simulação ---
SIMULATION_DURATION_SECONDS = 180  # Total duration of the simulation
ATTACK_START_TIME_SECONDS = 30     # When the attack begins
ATTACK_DURATION_SECONDS = 60       # How long the attack lasts

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
