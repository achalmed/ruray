"""lib/nucleo.py — raíz y logger de `core/` para las herramientas Python de identidad-visual (RQ-COD-06, P164).

Cada herramienta lo carga así (su carpeta está a N niveles de la raíz del repo):

    sys.path.insert(0, str(Path(__file__).resolve().parents[N]))
    from lib import nucleo
    log = nucleo.registro("identidad-visual.<herramienta>")

Da `RAIZ` (la raíz de este repo, por la ubicación del archivo: sirve igual en una copia o en un worktree),
`env` (el módulo `core/env.py`: `env.DOCS_ROOT`, `env.IDENTIDAD_VISUAL_DIR`, `env.SISTEMA_EDITORIAL_DIR`…) y
`registro()`, que delega en `core/py-common/logger.py` (misma línea que el logger Bash de `core/shell-lib`).

Límite: el repo es reutilizable por un despacho que no tenga el workspace; sin `core/` encima, `env` es None y
`registro()` usa `logging` con el mismo formato. Solo la librería estándar (el servidor no admite dependencias).
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FORMATO = "[%(levelname)s] %(asctime)s - %(message)s"     # el de core/py-common/logger.py


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _raiz_workspace():
    """La carpeta que contiene core/env.py, subiendo desde este repo (la misma búsqueda que documenta core/env.py)."""
    d = RAIZ
    while d != d.parent:
        if (d / "core" / "env.py").is_file():
            return d
        d = d.parent
    return None


_WS = _raiz_workspace()
env = _cargar("core_env", _WS / "core" / "env.py") if _WS else None
_logger_core = _cargar("core_logger", Path(env.PY_COMMON) / "logger.py") if env else None


def registro(nombre: str, verbose: bool = False) -> logging.Logger:
    """El logger de la herramienta: el de core/py-common si hay workspace; si no, uno equivalente de `logging`."""
    if _logger_core is not None:
        return _logger_core.configurar(nombre, verbose=verbose)
    log = logging.getLogger(nombre)
    if not log.handlers:
        log.setLevel(logging.DEBUG if verbose else logging.INFO)
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter(FORMATO, "%Y-%m-%d %H:%M:%S"))
        log.addHandler(h)
    return log


def abortar(log: logging.Logger, mensaje: str, codigo: int = 1):
    """Registra el error y sale con `codigo` (en lugar de `sys.exit("…")`, que no pasa por el logger)."""
    log.error(mensaje)
    sys.exit(codigo)
