"""estudio/tests/conftest.py — la raíz del estudio en sys.path (lib/) y el kit común (Unancha, UNANCHA_DIR) para las pruebas
que lo leen (fase 10.2b E0, 2026-10-20: las pruebas del servidor y del montaje vinieron de Unancha con su código)."""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from lib import nucleo  # noqa: E402  la raíz del espacio de trabajo (core/env.py), para hallar Unancha

# El kit común: UNANCHA_DIR o, en el espacio de trabajo, <DOCS_ROOT>/unancha. Va al entorno: el servidor lo lee al cargarse.
_kit = os.environ.get("UNANCHA_DIR") or (str(nucleo.env.DOCS_ROOT / "unancha") if nucleo.env else "")
KIT = Path(_kit) if _kit else None
if KIT is not None:
    os.environ["UNANCHA_DIR"] = str(KIT)


@pytest.fixture(scope="session")
def kit():
    if KIT is None or not (KIT / "tokens").is_dir():
        pytest.skip("sin el kit común: UNANCHA_DIR")
    return KIT


# Sin el kit común (fuera del espacio de trabajo, como en la demo pública), el servidor no carga sus colores ni su letra:
# las pruebas que lo cargan se saltan con su motivo, como las que piden la fixture `kit`.
NECESITAN_EL_KIT = {"test_servidor.py", "test_montaje.py", "test_kit.py"}


def pytest_collection_modifyitems(config, items):
    if KIT is not None and (KIT / "tokens").is_dir():
        return
    salto = pytest.mark.skip(reason="sin el kit común: UNANCHA_DIR")
    for item in items:
        if Path(str(item.fspath)).name in NECESITAN_EL_KIT:
            item.add_marker(salto)
