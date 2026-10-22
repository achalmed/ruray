"""estudio/tests/test_servidor.py — (vino de Unancha con el estudio, fase 10.2b E0) servidor del editor detrás de un proxy: prefijo público, Host/Origin y JSON."""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from conftest import RAIZ

SRV = RAIZ / "editor" / "servidor" / "servidor.py"


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("servidor_editor", SRV)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prefijo_se_normaliza(srv):
    assert srv.normalizar_prefijo("/estudio/") == "/estudio"
    assert srv.normalizar_prefijo("/a/b") == "/a/b"
    for malo in ("", "/", "estudio", "/../x", "/a b", "//x", "/x?y"):
        assert srv.normalizar_prefijo(malo) == ""


def test_sin_prefijo_acepta_las_dos_formas(srv):
    assert srv.sin_prefijo("/estudio/banco/a.jpg", "/estudio") == "/banco/a.jpg"
    assert srv.sin_prefijo("/banco/a.jpg", "/estudio") == "/banco/a.jpg"
    assert srv.sin_prefijo("/estudiox/banco/a.jpg", "/estudio") == "/estudiox/banco/a.jpg"


def test_host_y_origen(srv):
    ok = srv.peticion_permitida
    assert ok("GET", "127.0.0.1:8099", "")
    assert ok("POST", "localhost:8099", "http://localhost:8099")
    assert not ok("GET", "malicioso.example:8099", "")                 # DNS rebinding
    assert not ok("POST", "127.0.0.1:8099", "https://malicioso.example")  # CSRF
    assert not ok("POST", "127.0.0.1:8099", "null")
    assert ok("GET", "192.168.1.5:8099", "", red_local=True)           # HOST = 0.0.0.0
    assert srv.es_json("application/json; charset=utf-8") and not srv.es_json("text/plain")


def _puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_servidor_con_prefijo(tmp_path, kit):
    """Arranca el servidor con un perfil temporal y lo consulta como lo haría el proxy."""
    banco = tmp_path / "banco"
    (banco / "sub").mkdir(parents=True)
    (banco / "sub" / "foto.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    perfil = tmp_path / "perfil.json"
    rutas = {k: str(tmp_path / k) for k in ("redes", "transmisiones", "exports", "almacen", "proyectos_media",
                                             "proyectos_foto", "logos")}
    (tmp_path / "logos").mkdir()
    (tmp_path / "logos" / "marca.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    fuentes = tmp_path / "fuentes"
    fuentes.mkdir()
    fuente = kit / "logos-y-tipografias" / "excalifont-regular.ttf"   # del kit común (Unancha)
    (fuentes / fuente.name).write_bytes(fuente.read_bytes())
    perfil.write_text(json.dumps({"titular": {"nombre": "Persona de Prueba"}, "region": "Región de prueba",
                                  "rutas": {"banco": str(banco), "fuentes": str(fuentes), **rutas}}), encoding="utf-8")
    puerto = _puerto_libre()
    env = {**os.environ, "IDENTIDAD_PERFIL": str(perfil), "EDITOR_PUERTO": str(puerto)}
    env.pop("IDENTIDAD_BASE", None)
    proc = subprocess.Popen([sys.executable, str(SRV)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % puerto

    def pedir(ruta, datos=None, cabeceras=None):
        req = urllib.request.Request(base + ruta, data=datos, headers=cabeceras or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    try:
        for _ in range(50):
            try:
                if pedir("/api/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.1)
        # Suelto no anuncia Fototeca: el editor de piezas no ofrece «Guardar en la Fototeca».
        assert "fototeca" not in json.loads(pedir("/api/health")[1])
        # Sin prefijo, como siempre.
        assert json.loads(pedir("/api/imagenes")[1])[0]["url"] == "/banco/sub/foto.png"
        # Con prefijo del proxy.
        _, cuerpo = pedir("/api/imagenes", cabeceras={"X-Forwarded-Prefix": "/estudio"})
        assert json.loads(cuerpo)[0]["url"] == "/estudio/banco/sub/foto.png"
        # POST JSON: text/plain (formulario de otra página) no pasa; otro origen tampoco.
        assert pedir("/api/almacen", b"{}", {"Content-Type": "text/plain"})[0] == 415
        assert pedir("/api/almacen", b'{"clave":"x","datos":1}',
                     {"Content-Type": "application/json", "Origin": "https://malicioso.example"})[0] == 403
        assert pedir("/api/almacen", b'{"clave":"x","datos":1}', {"Content-Type": "application/json"})[0] == 200
        # Editor de fotos (foto.html): proyectos con capas y logos del perfil.
        doc = json.dumps({"nombre": "../fuera", "datos": {"info": {"width": 10}, "layers": []}}).encode()
        assert pedir("/api/proyecto-foto", doc, {"Content-Type": "application/json"})[0] == 200
        assert not (tmp_path / "fuera.json").exists()                       # el nombre se sanea: no sale de la carpeta
        lista = json.loads(pedir("/api/proyectos-foto")[1])
        assert [p["nombre"] for p in lista] == ["fuera"]
        assert json.loads(pedir("/api/proyecto-foto?nombre=fuera")[1])["datos"]["info"]["width"] == 10
        assert pedir("/api/proyecto-foto?nombre=nada")[0] == 404
        assert pedir("/api/proyecto-foto", b"{}", {"Content-Type": "application/json"})[0] == 400
        _, cuerpo = pedir("/api/logos", cabeceras={"X-Forwarded-Prefix": "/estudio"})
        assert json.loads(cuerpo) == [{"name": "marca.png", "url": "/estudio/logo/marca.png"}]
        # Una sola lista de logos: /api/logos es el alias de /api/design → marca.logos.
        marca = json.loads(pedir("/api/design")[1])["marca"]
        assert [(l["name"], l["url"]) for l in marca["logos"]] == [("marca.png", "/logo/marca.png")]
        # Marcadores {{…}} del perfil, con los neutros donde el perfil calla.
        assert marca["textos"]["titular"] == "Persona de Prueba" and marca["textos"]["region"] == "Región de prueba"
        assert marca["textos"]["sede"] == "Ciudad"
        # Tipografías del perfil con sus métricas de libass; el fotograma de un medio desconocido no existe.
        fuentes = json.loads(pedir("/api/fuentes")[1])
        propia = [f for f in fuentes["fuentes"] if f["origen"] == "perfil"]
        assert propia and propia[0]["familia"] == "Excalifont" and 0.3 < propia[0]["escala_ass"] < 1.2
        assert propia[0]["url"].startswith("/fuentes/")
        assert pedir("/api/fotograma?origen=/banco/nada.mp4&t=1")[0] == 404
        assert pedir("/fuentes-sistema/00000000/x.ttf")[0] == 404
        idiomas = json.loads(pedir("/api/video-config")[1])["idiomas"]
        assert "es" in idiomas["todos"] and "qu" not in idiomas["todos"]
        assert {"codigo": "qu", "nombre": "Quechua"} in idiomas["sin_soporte"]
    finally:
        proc.terminate()
        proc.wait(5)


def test_metricas_de_fuente(srv, kit):
    m = srv.metricas_fuente(str(kit / "logos-y-tipografias" / "excalifont-regular.ttf"))
    assert m["familia"] == "Excalifont" and m["peso"] == 400 and not m["cursiva"]
    assert 0.5 < m["escala_ass"] < 1 and 0.5 < m["ascenso_ass"] < 1
    assert srv.metricas_fuente("/no/existe.ttf") == {}


def test_textos_del_perfil(srv):
    t = srv.textos_perfil({"titular": {"nombre": "A", "rol": "B"}, "region": "R", "textos": {"lema": "L", "Malo!": "x"}})
    assert (t["titular"], t["cargo"], t["region"], t["lema"]) == ("A", "B", "R", "L")
    assert t["sede"] == srv.TEXTOS_NEUTROS["sede"] and "Malo!" not in t
    assert srv.idioma_whisper("en") == "en" and srv.idioma_whisper("qu") == "es" and srv.idioma_whisper("auto") is None


def test_textos_neutros_iguales_en_los_editores(srv, kit):
    """Los neutros de los marcadores {{…}} son los mismos en el servidor y en plantillas/base/perfil.js; y las plantillas
    ya no nombran una región ni un cargo concretos (las páginas de los editores salieron el 2026-10-21 con cada uno:
    media.html con Tullpu y editor.html con Awana, que lo comprueban en su tests/test_paginas.py)."""
    import re
    # Los editores viven en el estudio (qillqa); las plantillas, en el kit común (Unancha).
    for base, ruta in ((kit, "plantillas/base/perfil.js"),):
        texto = (base / ruta).read_text(encoding="utf-8")
        for k, v in srv.TEXTOS_NEUTROS.items():
            assert re.search(r'\b%s\s*:\s*"%s"' % (k, re.escape(v)), texto), (ruta, k)
    vetados = re.compile(r"Ayacucho|Huamanga|Huanta|SUTEP|DIPUTADO DE LA REPÚBLICA|CÁMARA DE DIPUTADOS", re.I)
    for f in list((kit / "plantillas").rglob("*.html")):
        assert not vetados.search(f.read_text(encoding="utf-8")), f
