#!/usr/bin/env python3
"""
PipelineModeling — unified workspace CLI.

Usage:
  python manage.py setup
  python manage.py start
  python manage.py stop
  python manage.py status
  python manage.py test [--unit | --integration]
  python manage.py simulate [--scenario {drift,version-fail,training-errors,chaos,all}]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable, NoReturn

# ── Constants ─────────────────────────────────────────────────────────────────

ROOT   = Path(__file__).parent.resolve()
VENV   = ROOT / ".venv"
IS_WIN = platform.system() == "Windows"
_BIN   = VENV / ("Scripts" if IS_WIN else "bin")

PYTHON    = _BIN / "python"
PIP       = _BIN / "pip"
PYTEST    = _BIN / "pytest"
UVICORN   = _BIN / "uvicorn"
STREAMLIT = _BIN / "streamlit"
PIDS_FILE = ROOT / ".pids.json"

REQUIREMENTS = [
    "services/api/requirements.txt",
    "services/frontend/requirements.txt",
    "services/seeder/requirements.txt",
    "model/requirements.txt",
    "tests/requirements.txt",
]

# service name → container name
_DOCKER = {
    "mlflow":         "pipeline_mlflow",
    "otel-collector": "pipeline_otel_collector",
}

# ── Output helpers ────────────────────────────────────────────────────────────

def _header(msg: str) -> None:   print(f"\n  {msg}")
def _step(msg: str)   -> None:   print(f"  >>     {msg}")
def _ok(msg: str)     -> None:   print(f"  [OK]   {msg}")
def _warn(msg: str)   -> None:   print(f"  [WARN] {msg}", file=sys.stderr)
def _fail(msg: str)   -> NoReturn:
    print(f"\n  [FAIL] {msg}\n", file=sys.stderr)
    sys.exit(1)

# ── Utilities ─────────────────────────────────────────────────────────────────

def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _api_healthy(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    try:
        if IS_WIN:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True,
            )
            return str(pid) in r.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _load_pids() -> dict[str, int]:
    if PIDS_FILE.exists():
        return json.loads(PIDS_FILE.read_text())
    return {}


def _save_pids(pids: dict[str, int]) -> None:
    PIDS_FILE.write_text(json.dumps(pids, indent=2))


def _load_dotenv() -> dict[str, str]:
    env_file = ROOT / ".env"
    result: dict[str, str] = {}
    if not env_file.exists():
        return result
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _docker_compose(*args: str) -> int:
    return subprocess.run(["docker", "compose", *args], cwd=ROOT).returncode


def _run_bg(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> int:
    """Spawn a process detached from the current terminal; return its PID."""
    merged = {**os.environ, **(env or {})}
    kwargs: dict = dict(args=cmd, cwd=str(cwd or ROOT), env=merged, stdin=subprocess.DEVNULL)
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    else:
        kwargs["start_new_session"] = True
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    return subprocess.Popen(**kwargs).pid


def _require_venv() -> None:
    if not VENV.exists() or not PYTHON.exists():
        _fail(".venv no encontrado. Ejecuta primero: python manage.py setup")

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_setup(_: argparse.Namespace) -> None:
    _header("PipelineModeling — setup")

    _step("Verificando Python 3.11+...")
    out = subprocess.run([sys.executable, "--version"], capture_output=True, text=True)
    _ok(out.stdout.strip() or out.stderr.strip())

    _step("Creando entorno virtual .venv...")
    if VENV.exists():
        _ok(".venv ya existe")
    else:
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
        _ok(".venv creado")

    _step("Instalando dependencias...")
    for req in REQUIREMENTS:
        path = ROOT / req
        if path.exists():
            subprocess.run([str(PIP), "install", "-q", "-r", str(path)], check=True)
            _ok(req)

    _step("Configurando .env...")
    env_file = ROOT / ".env"
    if not env_file.exists():
        shutil.copy(ROOT / ".env.example", env_file)
        _ok(".env creado desde .env.example")
    else:
        _ok(".env ya existe")

    _step("Verificando Docker...")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        _warn("Docker Desktop no esta corriendo. Necesario para MLflow y OTel Collector.")
    else:
        _ok("Docker OK")

    _step("Verificando modelo inicial...")
    model_pkl = ROOT / "model/weights/model.pkl"
    if not model_pkl.exists():
        _step("Entrenando modelo inicial...")
        subprocess.run([str(PYTHON), str(ROOT / "model/train.py")], check=True, cwd=ROOT)
        _ok("Modelo inicial entrenado")
    else:
        _ok("model.pkl ya existe")

    print()
    print("  ============================================")
    print("  Setup completado. Siguiente paso:")
    print("    python manage.py start")
    print("  ============================================\n")


def cmd_start(_: argparse.Namespace) -> None:
    _header("PipelineModeling — start")
    _require_venv()

    _step("Arrancando MLflow + OTel Collector...")
    if _docker_compose("up", "-d", *_DOCKER.keys()) != 0:
        _fail("docker compose up fallo.")
    _ok("MLflow :5000  OTel Collector :4317/:4318/:55679")

    env_file = ROOT / ".env"
    if not env_file.exists():
        shutil.copy(ROOT / ".env.example", env_file)

    model_pkl = ROOT / "model/weights/model.pkl"
    if not model_pkl.exists():
        _step("Entrenando modelo inicial...")
        subprocess.run([str(PYTHON), str(ROOT / "model/train.py")], check=True, cwd=ROOT)
        _ok("Modelo inicial entrenado")

    dotenv = _load_dotenv()

    _step("Arrancando API...")
    api_pid = _run_bg(
        [str(UVICORN), "main:app", "--reload", "--port", "8000", "--log-level", "info"],
        env={
            "MODEL_PATH":               str(ROOT / "model/weights/model.pkl"),
            "MLFLOW_TRACKING_URI":      dotenv.get("MLFLOW_TRACKING_URI", "http://localhost:5000"),
            "MLFLOW_MODEL_NAME":        dotenv.get("MLFLOW_MODEL_NAME",   "pipeline-model"),
            "ENABLE_DEBUG_ENDPOINTS":   "true",
        },
        cwd=ROOT / "services/api",
    )

    _step("Esperando a que la API este sana (hasta 60s)...")
    deadline = time.time() + 60
    while time.time() < deadline:
        if _api_healthy():
            _ok("API lista")
            break
        time.sleep(2)
    else:
        _fail("La API no respondio en 60s. Revisa el proceso uvicorn.")

    _step("Arrancando Frontend...")
    frontend_pid = _run_bg(
        [str(STREAMLIT), "run", str(ROOT / "services/frontend/app.py"),
         "--server.port", "8501", "--server.headless", "true"],
        env={
            "API_URL":    "http://localhost:8000",
            "MLFLOW_URL": dotenv.get("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        },
    )

    _step("Arrancando Seeder...")
    seeder_pid = _run_bg(
        [str(PYTHON), str(ROOT / "services/seeder/seeder.py")],
        env={
            "API_URL":               "http://localhost:8000",
            "REQUESTS_PER_SECOND":   dotenv.get("REQUESTS_PER_SECOND",   "20"),
            "INFERENCE_CONCURRENCY": dotenv.get("INFERENCE_CONCURRENCY", "10"),
            "TRAINING_INTERVAL_S":   dotenv.get("TRAINING_INTERVAL_S",   "30"),
            "TRAINING_BATCH_SIZE":   dotenv.get("TRAINING_BATCH_SIZE",   "50"),
            "DRIFT_ONSET_AFTER_S":   dotenv.get("DRIFT_ONSET_AFTER_S",   "120"),
            "DRIFT_MAGNITUDE":       dotenv.get("DRIFT_MAGNITUDE",        "2.0"),
        },
    )

    _save_pids({"api": api_pid, "frontend": frontend_pid, "seeder": seeder_pid})

    print()
    print("  ============================================")
    print("   PipelineModeling workspace activo")
    print("  ============================================")
    print("   Frontend       http://localhost:8501")
    print("   API (Swagger)  http://localhost:8000/docs")
    print("   API Health     http://localhost:8000/health")
    print("   MLflow UI      http://localhost:5000")
    print("   OTel zPages    http://localhost:55679")
    print("  ============================================")
    print("   Parar: python manage.py stop")
    print("  ============================================\n")


def cmd_stop(_: argparse.Namespace) -> None:
    _header("PipelineModeling — stop")

    pids = _load_pids()
    for svc, pid in pids.items():
        _step(f"Parando {svc} (PID {pid})...")
        try:
            if IS_WIN:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True
                )
            else:
                import signal
                os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception:
            pass

    for port in (8000, 8501):
        if _port_in_use(port):
            _step(f"Liberando puerto {port}...")
            if IS_WIN:
                r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
                for line in r.stdout.splitlines():
                    if f":{port}" in line and "LISTENING" in line:
                        pid_str = line.split()[-1]
                        subprocess.run(
                            ["taskkill", "/F", "/PID", pid_str], capture_output=True
                        )
            else:
                subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)

    _step("Parando contenedores Docker...")
    _docker_compose("stop", *_DOCKER.keys())

    PIDS_FILE.unlink(missing_ok=True)
    _ok("Todos los servicios parados.\n")


def cmd_status(_: argparse.Namespace) -> None:
    _header("PipelineModeling — status\n")

    pids = _load_pids()
    for svc in ("api", "frontend", "seeder"):
        pid = pids.get(svc)
        if pid:
            state = "[RUNNING]" if _pid_alive(pid) else "[STOPPED]"
            print(f"  {svc:<14} PID {pid:<8} {state}")
        else:
            print(f"  {svc:<14} [NO PID]")

    print()
    if _api_healthy():
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as r:
                body = json.loads(r.read())
            print(f"  API Health     [OK]  model_loaded={body.get('model_loaded')}  "
                  f"version={body.get('model_version')}")
        except Exception:
            print("  API Health     [OK]")
    else:
        print("  API Health     [UNREACHABLE]")

    print()
    for svc, container in _DOCKER.items():
        r = subprocess.run(
            ["docker", "inspect", "--format={{.State.Status}}", container],
            capture_output=True, text=True,
        )
        state = r.stdout.strip() if r.returncode == 0 else "stopped"
        print(f"  {svc:<22} {'[RUNNING]' if state == 'running' else '[STOPPED]'}")
    print()


def cmd_test(args: argparse.Namespace) -> None:
    _header("PipelineModeling — test")
    if not PYTEST.exists():
        _fail("pytest no encontrado. Ejecuta: python manage.py setup")

    cmd = [str(PYTEST), str(ROOT / "tests")]
    env = dict(os.environ)

    if getattr(args, "unit", False):
        cmd += ["-k", "not TestAPIEndpoints"]
    elif getattr(args, "integration", False):
        if not _api_healthy():
            _fail("La API no esta disponible. Ejecuta: python manage.py start")
        env.setdefault("API_URL", "http://localhost:8000")

    print()
    result = subprocess.run(cmd, cwd=ROOT, env=env)
    print()
    if result.returncode != 0:
        _fail(f"Algunos tests fallaron (exit code {result.returncode}).")
    _ok("Todos los tests pasaron.")

# ── Simulate scenarios ────────────────────────────────────────────────────────

_SAMPLE_NORMAL = [
    17.99, 10.38, 122.80, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.07871,
     1.095,  0.9053,  8.589,  153.4, 0.006399, 0.04904, 0.05373, 0.01587, 0.03003, 0.006193,
    25.38, 17.33,  184.60, 2019.0, 0.1622,  0.6656,  0.7119,  0.2654,  0.4601,  0.1189,
]
_SAMPLE_DRIFTED = [v * 10.0 for v in _SAMPLE_NORMAL]


def _post(path: str, body: dict, base: str = "http://127.0.0.1:8000") -> int:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        f"{base}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except Exception:
        return 0


def _sim_drift() -> None:
    print("  Escenario : DataDrift — features x10 durante 7 min")
    print("  OTel      : pipeline.data.drift_score emitido por DriftTracker")
    print()
    duration = 420
    deadline = time.time() + duration
    iteration = 0
    while time.time() < deadline:
        iteration += 1
        for _ in range(60):
            _post("/infer/", {"features": _SAMPLE_DRIFTED})
        print(f"\r  iter={iteration} | faltan {int(deadline - time.time())}s", end="", flush=True)
        time.sleep(8)
    print()
    _ok("DataDrift terminado. Observa: docker compose logs otel-collector --follow")


def _sim_version_fail() -> None:
    print("  Escenario : VersionSwitchFailed — model_ref inexistente en MLflow")
    print()
    status = _post("/version/switch", {"model_ref": "nonexistent-simulate-999"})
    _ok(f"Peticion enviada (HTTP {status}). "
        f"Metrica pipeline.version_switch.error incrementada.")
    print("  Observa  : docker compose logs otel-collector --follow")


def _sim_training_errors() -> None:
    print("  Escenario : HighTrainingErrorRate — label=2 fuera de classes=[0,1]")
    print()
    duration = 420
    deadline = time.time() + duration
    iteration = 0
    while time.time() < deadline:
        iteration += 1
        for _ in range(8):
            _post("/train/", {"features": [_SAMPLE_NORMAL], "labels": [2]})
        for _ in range(2):
            _post("/train/", {"features": [_SAMPLE_NORMAL], "labels": [0]})
        print(f"\r  iter={iteration} | faltan {int(deadline - time.time())}s", end="", flush=True)
        time.sleep(10)
    print()
    _ok("TrainingErrors terminado. Observa: docker compose logs otel-collector --follow")


def _sim_chaos() -> None:
    print("  Escenario : InferenceErrors — chaos 20% (requiere ENABLE_DEBUG_ENDPOINTS=true)")
    print()
    r = _post("/debug/chaos", {"inference_error_rate": 0.20})
    if r == 0:
        _warn("El endpoint /debug/chaos no responde.")
        _warn("Asegurate de arrancar con ENABLE_DEBUG_ENDPOINTS=true en .env")
        return
    _ok(f"Chaos activado (HTTP {r})")

    duration = 240
    deadline = time.time() + duration
    iteration = 0
    while time.time() < deadline:
        iteration += 1
        for _ in range(30):
            _post("/infer/", {"features": _SAMPLE_NORMAL})
        print(f"\r  iter={iteration} | faltan {int(deadline - time.time())}s", end="", flush=True)
        time.sleep(10)
    print()

    _post("/debug/chaos/reset", {})
    _ok("Chaos reseteado. Observa: docker compose logs otel-collector --follow")


_SCENARIOS: dict[str, Callable[[], None]] = {
    "drift":            _sim_drift,
    "version-fail":     _sim_version_fail,
    "training-errors":  _sim_training_errors,
    "chaos":            _sim_chaos,
}


def cmd_simulate(args: argparse.Namespace) -> None:
    _header("PipelineModeling — simulate")
    if not _api_healthy():
        _fail("La API no esta disponible. Ejecuta: python manage.py start")

    if args.scenario == "all":
        for name, fn in _SCENARIOS.items():
            print(f"\n  -- {name} " + "-" * (40 - len(name)))
            fn()
        return

    fn = _SCENARIOS.get(args.scenario)
    if fn is None:
        _fail(f"Escenario desconocido: {args.scenario}")
    print(f"\n  -- {args.scenario} " + "-" * (40 - len(args.scenario)))
    fn()

# ── Parser and dispatch ───────────────────────────────────────────────────────

_COMMANDS: dict[str, Callable[[argparse.Namespace], None]] = {
    "setup":    cmd_setup,
    "start":    cmd_start,
    "stop":     cmd_stop,
    "status":   cmd_status,
    "test":     cmd_test,
    "simulate": cmd_simulate,
}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="manage.py",
        description="PipelineModeling — unified workspace CLI",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    sub.add_parser("setup",  help="Primera configuracion (venv, deps, .env, modelo)")
    sub.add_parser("start",  help="Arrancar el stack completo")
    sub.add_parser("stop",   help="Parar todos los servicios")
    sub.add_parser("status", help="Estado de los servicios")

    t = sub.add_parser("test", help="Ejecutar la suite de tests")
    tg = t.add_mutually_exclusive_group()
    tg.add_argument("--unit",        action="store_true",
                    help="Solo tests unitarios (sin API)")
    tg.add_argument("--integration", action="store_true",
                    help="Solo tests de integracion (requiere API)")

    sim = sub.add_parser("simulate", help="Simular escenarios de carga y alertas")
    sim.add_argument(
        "--scenario",
        choices=[*_SCENARIOS.keys(), "all"],
        default="all",
        metavar="{" + ",".join([*_SCENARIOS.keys(), "all"]) + "}",
        help="Escenario a simular (default: all)",
    )

    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    _COMMANDS[args.command](args)
