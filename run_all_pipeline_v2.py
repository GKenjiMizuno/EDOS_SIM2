import subprocess
import sys
import time

# Encadeador da leva de tarefas combinada com o usuário: 5 (ataque isolado)
# -> 6a (completar 150/350 + reps até 10) -> 6b (pow2 base 20, reaproveita
# o 40 da 6a). Para o pipeline inteiro se qualquer etapa falhar, em vez de
# seguir com dado incompleto -- mesmo padrão de run_all_pipeline.py.

STEPS = [
    ("run_ataque_isolado.py", []),
    ("plot_ataque_isolado.py", []),
    ("run_graph4_completar_150_350.py", []),
    ("plot_graph4_reproducibilidade_refinada.py", []),
    ("plot_graph4_reproducibilidade_media_scaleup.py", []),
    ("plot_graph4_pico_pre_escalonamento.py", []),
    ("run_graph4_pow2_base20.py", []),
    ("plot_graph4_pow2_base20.py", []),
]


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def run_step(script, extra_args):
    cmd = ["python3", script] + extra_args
    log(f"===== Iniciando etapa: {' '.join(cmd)} =====")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        log(f"!!!!! Etapa {script} terminou com código {result.returncode} -- PARANDO o pipeline. !!!!!")
        sys.exit(result.returncode)
    log(f"===== Etapa concluída: {script} =====")


def main():
    for script, extra_args in STEPS:
        run_step(script, extra_args)
    log("PIPELINE_COMPLETO -- todas as etapas (5, 6a, 6b) terminaram com sucesso.")


if __name__ == "__main__":
    main()
