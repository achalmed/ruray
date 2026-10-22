"""ruray/pruebas.py — el entorno de prueba común de los editores (Tullpu, Kuyuy, Awana; 2026-10-21, al nacer Tullpu).

Venía de las pruebas del editor de fotos en Qillqa (backend/tests/test_tullpu.py), de donde lo tomaban también las de
videos y piezas. Ahora vive con la base: cada editor, en su repositorio o dentro de Qillqa, prueba con el mismo
servidor del estudio cargado sobre un perfil temporal y la misma Mediateca falsa.

    from ruray.pruebas import PNG, SECRETO, MediatecaFalsa, entorno   # noqa: F401 — `entorno` es un fixture de pytest

- `entorno`: carga el servidor del estudio con un perfil temporal (banco, almacén, proyectos y salidas en tmp_path) y
  el kit común de Unancha (UNANCHA_DIR o la carpeta hermana `unancha`); sin Unancha, la prueba se salta. Da
  (tmp_path, servidor). Nada toca las carpetas del verde ni las de Unancha.
- `MediatecaFalsa`: lo que el puente usa de «medios.v2», en memoria (una foto, la n.º 5, y lo que entra).

Solo para pruebas: importa pytest.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from ruray import comun, mediateca

UNANCHA = Path(os.environ.get("UNANCHA_DIR") or Path(__file__).resolve().parents[2] / "unancha")
SECRETO = "s" * 48
# Un PNG de 1×1 (gris).
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=")


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    if not (UNANCHA / "tokens" / "colors.json").is_file():
        pytest.skip("sin Unancha en esta máquina")
    rutas = {k: str(tmp_path / k) for k in ("banco", "almacen", "proyectos_media", "proyectos_foto", "exports")}
    rutas.update({"redes": str(tmp_path / "salida" / "redes"), "transmisiones": str(tmp_path / "salida" / "transmisiones")})
    (tmp_path / "banco" / "actividad").mkdir(parents=True)
    (tmp_path / "banco" / "actividad" / "plaza.png").write_bytes(PNG)
    (tmp_path / "perfil.json").write_text(json.dumps({"rutas": rutas}), encoding="utf-8")
    monkeypatch.setenv("UNANCHA_DIR", str(UNANCHA))
    monkeypatch.setenv("IDENTIDAD_PERFIL", str(tmp_path / "perfil.json"))
    monkeypatch.setattr(comun.config, "jwt_secret", SECRETO)
    # Sin Mediateca salvo en las pruebas del puente (otra prueba puede dejar activo el anfitrión de Qillqa).
    monkeypatch.setattr(mediateca, "con_mediateca", lambda: False)
    srv = comun.recargar()
    yield tmp_path, srv
    comun._servidor = None


class MediatecaFalsa:
    """Lo que el puente usa de «medios.v2», en memoria: una foto (n.º 5) y lo que entra."""

    class ErrorFototeca(Exception):
        pass

    def __init__(self, raiz: Path) -> None:
        self.dir, self.ingresos = raiz, []
        (raiz / ".subidas").mkdir(parents=True)
        (raiz / "derivado.jpg").write_bytes(PNG)
        (raiz / "2026").mkdir()

    def raiz(self):
        return self.dir

    def admitido(self, ruta):
        return str(ruta).lower().endswith((".jpg", ".png"))

    def es_video(self, ruta):
        return str(ruta).lower().endswith(".mp4")

    def carpeta_temporal(self):
        return self.dir / ".subidas"

    def clave_ajustes(self, ajustes):
        return "0"

    def exportar(self, archivo, sha, ajustes, preset, formato):
        return self.dir / "derivado.jpg"

    def derivado(self, archivo, sha, ajustes, preset):
        return self.dir / "derivado.jpg"

    def ruta_original(self, archivo):
        return self.dir / archivo

    async def fotos_para_editor(self, album, limite):
        return [{"id": 5, "titulo": "Visita", "nombre_original": "IMG_5.jpg", "album": album, "version": "0"}]

    async def foto_vigente(self, foto_id):
        return {"id": 5, "archivo": "o/5.jpg", "sha256": "ab", "ajustes": {}, "medio": "foto", "titulo": "Visita",
                "nombre_original": "IMG_5.jpg", "version": "0"} if foto_id == 5 else None

    async def pieza_vigente(self, archivo, ambito):
        return {"archivo": archivo} if ambito == "prensa" and (self.dir / archivo).is_file() else None

    async def ingresar(self, ruta, nombre, usuario_id, *, metadatos=None, **resto):
        archivo = f"2026/20261020_1200{len(self.ingresos):02d}{ruta.suffix}"
        ruta.replace(self.dir / archivo)
        self.ingresos.append({"nombre": nombre, "usuario_id": usuario_id, **resto,
                              "metadatos": metadatos("foto", 1080, 1350) if metadatos else None})
        return {"id": 40 + len(self.ingresos), "nueva": True, "archivo": archivo}
