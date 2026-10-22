"""estudio/tests/test_herramientas.py — Inkscape y GIMP sin interfaz se eligen desde lib/herramientas.py, sin código de Unancha
(fase 10.2b, 2026-10-21: `shorts.py portadas` y `editor/lote_gimp.py` importaban `adaptadores.lib.herramientas`, que en qillqa no
existe). Las pruebas no necesitan Inkscape ni GIMP: el PATH es una carpeta temporal con ejecutables falsos."""
import importlib.util

import pytest

from conftest import RAIZ
from lib import herramientas


def _ejecutable(carpeta, nombre):
    ruta = carpeta / nombre
    ruta.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ruta.chmod(0o755)
    return str(ruta)


def _cargar(nombre, relativa):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / relativa)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def path_falso(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    return tmp_path


def test_nativo_manda(path_falso):
    ruta = _ejecutable(path_falso, "gimp-console-3")
    assert herramientas.herramienta("gimp-console") == ([ruta], "APT")


def test_flatpak_si_no_hay_nativo(path_falso, monkeypatch):
    monkeypatch.setattr(herramientas, "flatpak_tiene", lambda app: app == "org.gimp.GIMP")
    assert herramientas.herramienta("gimp-console") == (
        ["flatpak", "run", "--command=gimp-console", "org.gimp.GIMP"], "Flatpak")
    assert herramientas.herramienta("inkscape") == (None, None)


def test_ninguna(path_falso):
    assert herramientas.herramienta("inkscape") == (None, None)   # sin flatpak en el PATH


@pytest.mark.parametrize("relativa, funcion, nombre", [
    ("video/shorts/shorts.py", "_inkscape", "inkscape"),
    ("editor/lote_gimp.py", "gimp_console", "gimp-console"),
])
def test_el_estudio_la_usa(relativa, funcion, nombre, path_falso):
    """Los dos llamadores resuelven la orden aquí, sin `adaptadores/` (que solo existe en Unancha)."""
    assert "adaptadores" not in (RAIZ / relativa).read_text(encoding="utf-8").split("def " + funcion)[1].split("\ndef ")[0]
    ruta = _ejecutable(path_falso, nombre)
    mod = _cargar("estudio_" + funcion, relativa)
    assert getattr(mod, funcion)() == [ruta]
