"""estudio/tests/test_kit.py — el estudio y el kit común no se desfasan (fase 10.2b E0, 2026-10-20).

Los colores de los editores son bloques GENERADOS desde los tokens de Unancha (`tokens:inicio … tokens:fin` y
`tokens-color:inicio … tokens-color:fin`). Mientras el generador de Unancha (adaptadores/lib/web.py) siga escribiendo en
su copia de `editor/`, la copia de qillqa debe tener los mismos bloques: si cambia un token, esta prueba lo avisa y los
bloques se copian de Unancha (o, desde E2–E4, cada editor los genera él mismo desde los tokens).
"""
import json
import subprocess
import sys

import pytest

from conftest import RAIZ

# Cada bloque generado del estudio: (archivo del estudio, marcas, cómo lo calcula el generador de Unancha).
BLOQUES = (
    ("editor/estudio-tema.css", "MARCAS_CSS", "bloque_css"),
)


@pytest.fixture(scope="module")
def web(kit):
    """Las marcas y los bloques que HOY da el generador de Unancha, calculados en su propio proceso (su `lib` y su raíz,
    no los del estudio)."""
    codigo = ("import json, sys; sys.path.insert(0, '.'); from adaptadores.lib import web as w; "
              "print(json.dumps({'MARCAS_JS': w.MARCAS_JS, 'MARCAS_CSS': w.MARCAS_CSS, "
              "'bloque_editor': w.bloque_editor(), 'bloque_css': w.bloque_css()}))")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=kit, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout)


@pytest.mark.parametrize("archivo,marcas,cuerpo", BLOQUES)
def test_los_bloques_de_tokens_del_estudio_son_los_del_kit(web, archivo, marcas, cuerpo):
    texto = (RAIZ / archivo).read_text(encoding="utf-8")
    inicio, fin = web[marcas]
    a, b = texto.find(inicio), texto.find(fin)
    assert a >= 0 and b > a, f"{archivo} no tiene las marcas {inicio} … {fin}"
    assert texto[a:b + len(fin)] == web[cuerpo], f"{archivo}: el bloque de tokens no es el que hoy da Unancha"
