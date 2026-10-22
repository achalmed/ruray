"""ruray/comun.py — la base común de los editores del estudio (Ruray; nació en Qillqa el 2026-10-20, fase 10.2b E2a, y
salió a su repositorio el 2026-10-21).

Los editores de Prensa vinieron de Unancha con su servidor aparte (`estudio/editor/servidor/servidor.py`, E0). Aquí
ese servidor se porta UNA vez a FastAPI. Sus funciones (el banco, el kit común, el almacén, la mejora de fotos…) se
cargan del código del estudio tal cual. Cada editor (Tullpu, fotos; Kuyuy, videos; Awana, piezas) monta solo las rutas
que le tocan bajo su prefijo, con sus páginas y su cookie:

    EDITOR = Editor(id="fotos", nombre="Editor de fotos", prefijo="/api/fotos", inicio="foto.html",
                    paginas=("foto.html", "vendor/minipaint/"), rutas=COMUNES | {"GET api/proyectos-foto", …},
                    carpeta=Path(__file__).resolve().parents[1] / "paginas")   # sus páginas, en su repositorio
    router = crear_router(EDITOR)

- Las páginas piden todo RELATIVO a su carpeta (`api("/api/x")` → `<prefijo>/api/x`): se sirven sin tocarlas.
- Las URL que emite el servidor llevan el prefijo del editor (su prefijo por hilo, `_LOCAL.prefijo`): cada función
  corre en un hilo que lo fija antes (`_en_hilo`).
- `POST <prefijo>/traer/{id}` (con la ficha): «Usar en Prensa» de la Mediateca, la foto en el banco del editor.
- El marco (iframe) no manda la ficha de la API. `POST <prefijo>/sesion` (con la ficha) da la cookie del editor,
  firmada con un secreto derivado de JWT_SECRET, solo para su prefijo (HttpOnly, SameSite=Strict). El resto la exige.
- Con la Mediateca (si el anfitrión ofrece «medios.v2»; ruray/mediateca.py): el selector la incluye, sus
  fotos se materializan en el banco, y lo exportado y lo subido entran a ella. La sesión puede llevar la pieza de prensa
  para la que se abrió (`{pieza: N}`, resuelta por la referencia «piezas:pieza:N»): lo exportado queda vinculado a ella.
- Nada de Qillqa: solo Tiqsi (la cuenta, por `tiqsi.puertos.usuario_actual`; las fichas, por `tiqsi.minimo`).

Configuración: ESTUDIO_DIR (el código del estudio; por omisión `estudio/` de este repositorio), ESTUDIO_PYTHON (el intérprete de los
motores, que necesitan numpy y Pillow; por omisión `python3`) y JWT_SECRET. Las carpetas (banco, almacén, salidas) las
pone el perfil del estudio (IDENTIDAD_PERFIL) y el kit común, UNANCHA_DIR, como siempre.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import importlib.util
import json
import logging
import mimetypes
import os
import re
import shutil
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from tiqsi.minimo import firmar, leer
from tiqsi.anfitrion import activo
from tiqsi.modulo import resolver
from tiqsi.referencias import Referencia
from tiqsi.puertos import Usuario, usuario_actual

from ruray import mediateca as em

# El código del estudio que vino de Unancha (estudio/, E0), en este repositorio.
ESTUDIO_POR_OMISION = Path(__file__).resolve().parents[1] / "estudio"
MINUTOS_SESION = 120
# Lo que la carga del servidor deja en sys.modules con nombres genéricos: se retira para no tapar los de Qillqa.
_NOMBRES_DEL_ESTUDIO = ("config", "lib", "lib.nucleo", "montaje")


class ConfigEstudio(BaseSettings):
    estudio_dir: str = ""
    estudio_python: str = ""
    jwt_secret: str = ""
    # Dónde están las páginas de los OTROS editores (los enlaces «Publicaciones», «Editor de video» de cada página): una
    # carpeta para todas («/estudio/») o una por página («video.html=/api/videos/,*=/estudio/»); solo, ninguna.
    estudio_otras_paginas: str = ""


config = ConfigEstudio()


def raiz() -> Path:
    return Path(config.estudio_dir) if config.estudio_dir else ESTUDIO_POR_OMISION


def python() -> str:
    return config.estudio_python or shutil.which("python3") or sys.executable


# --- el servidor del estudio, cargado una vez ------------------------------------------------------------------


class _SysDelEstudio:
    """El `sys` que ve el servidor del estudio: el de siempre, salvo el intérprete de sus motores (`mejorar_foto.py`
    corre como subproceso con `sys.executable`, y el de la API no tiene numpy)."""

    def __init__(self, ejecutable: str) -> None:
        self.executable = ejecutable

    def __getattr__(self, nombre: str):
        return getattr(sys, nombre)


_servidor = None
_candado = threading.Lock()


def _cargar(carpeta: Path):
    ruta = carpeta / "editor" / "servidor" / "servidor.py"
    if not ruta.is_file():
        raise RuntimeError(f"No está el servidor del estudio en {ruta} (ESTUDIO_DIR).")
    camino = list(sys.path)
    ajenos = {n: sys.modules.pop(n) for n in _NOMBRES_DEL_ESTUDIO if n in sys.modules}
    try:
        spec = importlib.util.spec_from_file_location("estudio_servidor", ruta)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["estudio_servidor"] = mod
        spec.loader.exec_module(mod)
        # shorts.py (subtítulos y marca de los títulos) también inserta la raíz del estudio en sys.path al cargarse: se
        # carga aquí, dentro de esta ventana, y no en la primera petición de video.
        try:
            mod.montaje.shorts()
        except Exception as e:  # noqa: BLE001 — sin shorts, el editor de video pierde sus títulos, no el resto
            logging.getLogger("qillqa.estudio").warning("No se pudo cargar shorts.py del estudio: %s", e)
    except BaseException:
        sys.modules.pop("estudio_servidor", None)
        raise
    finally:
        sys.path[:] = camino
        for n in _NOMBRES_DEL_ESTUDIO:
            sys.modules.pop(n, None)
        sys.modules.update(ajenos)
    mod.sys = _SysDelEstudio(python())
    return mod


def servidor():
    """El módulo del servidor del estudio (sus funciones y sus carpetas), cargado la primera vez que se pide."""
    global _servidor
    with _candado:
        if _servidor is None:
            _servidor = _cargar(raiz())
        return _servidor


def recargar():
    """Vuelve a cargarlo (las pruebas cambian el perfil y el kit, que el servidor lee al cargarse)."""
    global _servidor
    with _candado:
        _servidor = None
    return servidor()


async def _en_hilo(prefijo: str, funcion, *args):
    """Corre una función del servidor en un hilo con el prefijo público del editor (sus URL lo llevan)."""
    srv = servidor()

    def correr():
        srv._LOCAL.prefijo = prefijo
        return funcion(*args)

    return await asyncio.to_thread(correr)


# --- el editor y su sesión -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Editor:
    id: str
    nombre: str
    prefijo: str            # «/api/fotos»: sus páginas, su API y su cookie viven debajo
    inicio: str             # la página que abre («foto.html»)
    paginas: tuple[str, ...]  # lo estático que sirve: archivos («foto.html») o carpetas («vendor/minipaint/»)
    rutas: frozenset[str] = field(default_factory=frozenset)   # «GET api/media», «POST api/subir», «GET banco/»…
    # La carpeta de sus páginas propias, en el repositorio del editor (Tullpu, 2026-10-21): lo de `paginas` se busca
    # primero ahí y, si no está, en el estudio (lo común: estudio-tema.css, estudio-iconos.js, estudio-movil.js).
    carpeta: Path | None = None

    @property
    def cookie(self) -> str:
        return f"estudio_{self.id}"


def _secreto(editor: Editor) -> str | None:
    """Un secreto propio de cada editor, derivado de JWT_SECRET: su cookie no vale como ficha de la API ni en otro
    editor."""
    base = config.jwt_secret or os.environ.get("JWT_SECRET", "")
    if len(base) < 32:
        return None
    return hmac.new(base.encode(), f"estudio:{editor.id}".encode(), hashlib.sha256).hexdigest()


def firmar_sesion(editor: Editor, usuario_id: int, rol: str, pieza: dict | None = None) -> tuple[str, datetime]:
    """La cookie del editor; `pieza` ({id, titular}) es la pieza de prensa para la que se abrió."""
    secreto = _secreto(editor)
    if secreto is None:
        raise HTTPException(503, "Falta JWT_SECRET (32 caracteres o más): el editor no puede abrir su sesión.")
    vence = datetime.now(timezone.utc) + timedelta(minutes=MINUTOS_SESION)
    datos = {"sub": str(usuario_id), "rol": rol, "aud": f"estudio:{editor.id}"}
    if pieza and isinstance(pieza.get("id"), int):
        datos["pieza"] = {"id": pieza["id"], "titular": " ".join(str(pieza.get("titular") or "").split())[:160]}
    return firmar(datos, secreto, MINUTOS_SESION), vence


def _hay_piezas() -> bool:
    """¿El anfitrión sabe resolver piezas de prensa? Solo, no: el editor se abre sin pieza."""
    try:
        return activo().referencias.sabe(Referencia("piezas", "pieza", "1"))
    except RuntimeError:
        return False


async def pieza_de(pieza_id: int | None) -> dict | None:
    """{id, titular} de una pieza de prensa por su referencia («piezas:pieza:N»); None si no hay quien la resuelva
    (el editor solo) o no existe."""
    if not pieza_id:
        return None
    try:
        r = await resolver(f"piezas:pieza:{int(pieza_id)}")
    except RuntimeError:   # sin anfitrión activo
        return None
    return {"id": int(pieza_id), "titular": r.get("titulo") or ""} if r else None


def leer_sesion(editor: Editor, valor: str | None) -> dict | None:
    """La carga de una cookie válida y vigente de ESTE editor, o None."""
    secreto = _secreto(editor)
    if not valor or secreto is None:
        return None
    datos = leer(valor, secreto)
    if not datos or datos.get("aud") != f"estudio:{editor.id}" or datos.get("rol") in ("", None, "invitado"):
        return None
    return datos


# --- respuestas --------------------------------------------------------------------------------------------------

# El editor solo se deja enmarcar por el propio sistema.
_MARCO = {"X-Frame-Options": "SAMEORIGIN", "Content-Security-Policy": "frame-ancestors 'self'"}


def _json(obj, codigo: int = 200) -> JSONResponse:
    return JSONResponse(obj, status_code=codigo, headers={"Cache-Control": "no-store", **_MARCO})


def _error(texto: str, codigo: int) -> JSONResponse:
    return _json({"ok": False, "error": texto}, codigo)


def _archivo(ruta: str | Path, cache: bool = False) -> Response:
    """Un archivo con rangos (videos) y el mismo Cache-Control del servidor del estudio."""
    ruta = Path(ruta)
    if not ruta.is_file():
        return _error("No encontrado", 404)
    tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
    if tipo.startswith("text/") or tipo in ("application/json", "text/javascript"):
        tipo += "; charset=utf-8"
    return FileResponse(ruta, media_type=tipo, headers={
        "Cache-Control": "private, max-age=3600" if cache else "no-store", **_MARCO})


def _servir_desde(base: str, rel: str) -> Response:
    srv = servidor()
    destino = os.path.normpath(os.path.join(base, rel))
    if not srv.dentro_de(base, destino):
        return _error("Prohibido", 403)
    return _archivo(destino)


def ruta_segura(ruta: str) -> str | None:
    """La ruta pedida, limpia, o None si intenta salir (se decodifica otra vez: «%2e%2e» doble es «..»)."""
    r = unquote(ruta or "")
    if "\x00" in r or "\\" in r or r.startswith("/"):
        return None
    partes = r.split("/")
    if any(p in ("..", ".") for p in partes) or any(p == "" for p in partes[:-1]):
        return None
    return r


def _pagina(titulo: str, detalle: str) -> str:
    return ("<!doctype html><meta charset=utf-8><title>Estudio</title>"
            "<body style=\"font:15px system-ui,sans-serif;color:#2b2522;background:#f7f5f2;padding:32px\">"
            f"<p style=\"font-weight:600\">{titulo}</p><p>{detalle}</p></body>")


def _sin_sesion(peticion: Request, editor: Editor) -> Response:
    if "text/html" in peticion.headers.get("accept", ""):
        return HTMLResponse(_pagina(f"Abra el {editor.nombre.lower()} desde el sistema.",
                                    "La sesión del editor venció o no se abrió."), status_code=401, headers=_MARCO)
    return _error("Sesión del editor vencida: recargue la página.", 401)


# --- lo que el servidor del estudio hacía en su Handler, portado ---------------------------------------------------


def _miniatura(rel: str) -> Response:
    """Miniatura ligera (~320 px, JPEG) de una imagen del banco, en caché por fecha; sin Pillow, el original."""
    srv = servidor()
    origen = os.path.normpath(os.path.join(srv.DIR_BANCO, rel))
    if not srv.dentro_de(srv.DIR_BANCO, origen):
        return _error("Prohibido", 403)
    if srv._PILImage is None or origen.lower().endswith(srv.EXTS_VIDEO + (".svg", ".gif")):
        return _archivo(origen)
    try:
        mt = int(os.path.getmtime(origen))
    except OSError:
        return _error("No encontrado", 404)
    cache_dir = os.path.join(srv.DIR_EXPORTS, "tmp", "miniaturas")
    destino = os.path.join(cache_dir, re.sub(r"[^\w]", "_", rel) + "-%d.jpg" % mt)
    if not os.path.exists(destino):
        try:
            os.makedirs(cache_dir, exist_ok=True)
            im = srv._PILImageOps.exif_transpose(srv._PILImage.open(origen))
            im.thumbnail((320, 320))
            im.convert("RGB").save(destino, "JPEG", quality=72)
        except Exception:
            return _archivo(origen)
    return _archivo(destino)


def _fuente_sistema(ident: str) -> Response:
    """Solo los archivos que /api/fuentes anunció (las familias de la marca instaladas): nunca una ruta libre."""
    srv = servidor()
    if not srv._FUENTES_SISTEMA:
        srv.listar_fuentes()
    destino = srv._FUENTES_SISTEMA.get(ident)
    return _archivo(destino, cache=True) if destino else _error("No encontrado", 404)


def _proyecto(carpeta: str, nombre: str) -> Response:
    srv = servidor()
    p = os.path.join(carpeta, srv.sanear_nombre(nombre) + ".json")
    if not (srv.dentro_de(carpeta, p) and os.path.exists(p)):
        return _error("No existe", 404)
    return _archivo(p)


def _guardar_proyecto(carpeta: str, cuerpo: dict) -> tuple[dict, int]:
    srv = servidor()
    nombre = srv.sanear_nombre(cuerpo.get("nombre") or "proyecto")
    datos = cuerpo.get("datos")
    if datos is None:
        return {"ok": False, "error": "Datos inválidos: faltan los datos"}, 400
    os.makedirs(carpeta, exist_ok=True)
    p = os.path.join(carpeta, nombre + ".json")
    if not srv.dentro_de(carpeta, p):
        return {"ok": False, "error": "Nombre no válido"}, 400
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"nombre": nombre, "datos": datos, "guardado": datetime.now().isoformat(timespec="seconds")},
                      f, ensure_ascii=False)
    except Exception as e:
        return {"ok": False, "error": "No se pudo guardar: %s" % e}, 500
    return {"ok": True, "nombre": nombre}, 200


def _guardar_almacen(cuerpo: dict) -> tuple[dict, int]:
    """{clave, datos} | {claves: {…}} | {clave, borrar: true}. 500 si ALGO no llegó al disco: el editor nunca da por
    guardado lo que no se guardó."""
    srv = servidor()
    if cuerpo.get("borrar") and "clave" in cuerpo:
        ok = srv.almacen_borrar(cuerpo.get("clave"))
        return {"ok": ok, "borrada": cuerpo.get("clave")}, 200 if ok else 500
    if isinstance(cuerpo.get("claves"), dict):
        pares = cuerpo["claves"]
    elif "clave" in cuerpo:
        pares = {cuerpo.get("clave"): cuerpo.get("datos")}
    else:
        return {"ok": False, "error": "Falta 'clave' o 'claves'"}, 400
    guardadas, fallidas = [], []
    for clave, datos in pares.items():
        (guardadas if srv.almacen_guardar(clave, datos) else fallidas).append(clave)
    if fallidas:
        return {"ok": False, "guardadas": guardadas, "fallidas": fallidas,
                "error": "No se pudo guardar: %s" % ", ".join(map(str, fallidas))}, 500
    return {"ok": True, "guardadas": guardadas}, 200


def _exportar_foto(cuerpo: dict) -> tuple[dict, int]:
    """La foto final a la salida de su canal (redes/<canal> o transmisiones) y una copia al banco con su crédito."""
    srv = servidor()
    try:
        nombre = srv.sanear_nombre(cuerpo.get("nombre") or "pieza.png")
        canal = cuerpo.get("canal", "")
        data_url = cuerpo.get("dataURL", "")
        datos = base64.b64decode(data_url.split(",", 1)[1] if "," in data_url else data_url)
    except Exception as e:
        return {"ok": False, "error": "Datos inválidos: %s" % e}, 400
    dest = srv.dir_canal(canal)
    os.makedirs(dest, exist_ok=True)
    salida = srv.ruta_libre(os.path.join(dest, "%s-%s" % (datetime.now().strftime("%Y-%m-%d"), nombre)))
    try:
        with open(salida, "wb") as f:
            f.write(datos)
    except Exception as e:
        return {"ok": False, "error": "No se pudo guardar: %s" % e}, 500
    banco_url = ""
    try:
        os.makedirs(srv.DIR_EDITADAS, exist_ok=True)
        destino_banco = srv.ruta_libre(os.path.join(srv.DIR_EDITADAS, os.path.basename(salida)))
        shutil.copy2(salida, destino_banco)
        rel = os.path.relpath(destino_banco, srv.DIR_BANCO)
        srv.anotar_credito(rel.replace(os.sep, "/"), srv._cfg("CREDITO_EDITADAS", "Pieza editada en el Editor"))
        banco_url = srv.pub("/banco/" + "/".join(quote(s) for s in rel.split(os.sep)))
    except Exception:
        pass
    return {"ok": True, "url": srv.url_canal(salida, canal), "banco_url": banco_url,
            "archivo": os.path.basename(salida)}, 200


def _analizar(cuerpo: dict) -> tuple[dict, int]:
    srv = servidor()
    ruta, _ = srv._resolver_origen(cuerpo)
    if not ruta:
        return {"ok": False, "error": "origen no válido"}, 400
    return srv.analizar_foto(ruta), 200


def _mejorar(cuerpo: dict) -> tuple[dict, int]:
    """La mejora NO destructiva: el resultado se guarda en caché por (origen, nivel, ajustes); la original no se toca."""
    srv = servidor()
    ruta, identidad = srv._resolver_origen(cuerpo)
    if not ruta:
        return {"ok": False, "error": "origen no válido"}, 400
    nivel = cuerpo.get("nivel", "auto")
    if nivel not in ("suave", "auto", "intensiva"):
        nivel = "auto"
    params = {k: cuerpo.get(k, -1) for k in ("nitidez", "ruido", "claridad", "contraste", "color", "luz", "resolucion")}
    os.makedirs(srv.DIR_MEJORADAS, exist_ok=True)
    salida = os.path.join(srv.DIR_MEJORADAS, "mej_" + srv._clave_mejora(identidad, nivel, params) + ".jpg")
    if not os.path.exists(salida):
        res = srv.mejorar_foto(ruta, salida, nivel, params)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error", "falló la mejora")}, 500
        info = res.get("analisis", {}) or {}
    else:
        info = srv.analizar_foto(ruta)
    return {"ok": True, "url": srv.pub("/exports/mejoradas/" + quote(os.path.basename(salida))), "nivel": nivel,
            "analisis": info}, 200


def _fuentes() -> dict:
    srv = servidor()
    marca = srv._marca_video()
    return {"ok": True, "fuentes": srv.listar_fuentes(), "textos": srv.textos_perfil(),
            "familias_marca": {"titular": marca.get("fuente_titular"), "texto": marca.get("fuente_texto")}}


# Lo que comparten los editores: el kit común, el banco, el almacén y las salidas por canal.
COMUNES = frozenset({
    "GET api/health", "GET api/design", "GET api/logos", "GET api/fuentes", "GET api/media", "GET api/almacen",
    "POST api/almacen", "POST api/subir",
    "GET miniatura/", "GET banco/", "GET plantillas/", "GET fuentes/", "GET fuentes-sistema/", "GET logo/",
    "GET exports/", "GET redes/", "GET transmisiones/", "GET mediateca/",
})

# Las rutas POST que reciben JSON (el resto, /api/subir, un cuerpo binario).
_POST_JSON = {"api/almacen", "api/exportar-foto", "api/proyecto-foto", "api/proyecto-media", "api/analizar-foto",
              "api/mejorar-foto", "api/fototeca-pieza", "api/imagenes", "api/exportar-video", "api/exportar-proyecto-video",
              "api/subtitular-video", "api/plan-video", "api/fototeca-video"}

# Las rutas del editor de videos (Kuyuy, E3): la cola de ffmpeg del estudio, el plan para ffmpeg.wasm y los fotogramas.
VIDEO = frozenset({
    "GET api/video-config", "GET api/trabajo", "GET api/fotograma", "POST api/exportar-video",
    "POST api/exportar-proyecto-video", "POST api/subtitular-video", "POST api/plan-video", "POST api/fototeca-video",
})


async def _cuerpo_json(peticion: Request, maximo: int) -> dict:
    if (peticion.headers.get("content-type") or "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Se espera application/json")
    largo = peticion.headers.get("content-length")
    if largo and largo.isdigit() and int(largo) > maximo:
        raise HTTPException(413, "El cuerpo supera %d MB" % (maximo >> 20))
    partes, total = [], 0
    async for trozo in peticion.stream():
        total += len(trozo)
        if total > maximo:
            raise HTTPException(413, "El cuerpo supera %d MB" % (maximo >> 20))
        partes.append(trozo)
    try:
        cuerpo = json.loads(b"".join(partes) or b"{}")
    except ValueError as e:
        raise HTTPException(400, "Datos inválidos: %s" % e) from e
    if not isinstance(cuerpo, dict):
        raise HTTPException(400, "Datos inválidos: se espera un objeto")
    return cuerpo


async def _subir(peticion: Request, editor: Editor, sesion: dict) -> Response:
    """Una foto, un video o un audio al banco (subidas-editor/): el cuerpo es el archivo; el nombre, X-Nombre."""
    srv = servidor()
    nombre = srv.sanear_nombre(unquote(peticion.headers.get("x-nombre", "") or ""))
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in srv.EXTS + srv.EXTS_VIDEO + srv.EXTS_AUDIO:
        return _error("Extensión no permitida: %s" % ext, 400)
    largo = peticion.headers.get("content-length")
    if largo and largo.isdigit() and int(largo) > srv.MAX_SUBIDA:
        return _error("El archivo supera %d MB" % (srv.MAX_SUBIDA >> 20), 413)
    os.makedirs(srv.DIR_SUBIDAS, exist_ok=True)
    destino = srv.ruta_libre(os.path.join(srv.DIR_SUBIDAS, nombre))
    total = 0
    try:
        with open(destino, "wb") as f:
            async for trozo in peticion.stream():
                total += len(trozo)
                if total > srv.MAX_SUBIDA:
                    raise HTTPException(413, "El archivo supera %d MB" % (srv.MAX_SUBIDA >> 20))
                await asyncio.to_thread(f.write, trozo)
    except HTTPException as e:
        os.remove(destino)
        return _error(e.detail, e.status_code)
    except Exception as e:
        return _error("No se pudo guardar: %s" % e, 500)
    rel = os.path.relpath(destino, srv.DIR_BANCO)
    datos = {"ok": True, "url": editor.prefijo + "/banco/" + "/".join(quote(s) for s in rel.split(os.sep)),
             "esVideo": ext in srv.EXTS_VIDEO, "esAudio": ext in srv.EXTS_AUDIO}
    # Una foto subida al editor es también una foto más de la Mediateca (etiqueta «Prensa»).
    if em.con_mediateca() and em.es_imagen(nombre):
        tmp = em.ft.carpeta_temporal() / f"{os.urandom(8).hex()}{ext}"
        try:
            await asyncio.to_thread(shutil.copyfile, destino, tmp)
            datos["fototeca"] = await em.ingresar_ruta(tmp, nombre, int(sesion["sub"]), pieza=False)
        except OSError:
            tmp.unlink(missing_ok=True)
    return _json(datos)


# Las páginas de los cuatro editores: las que no son de este llevan a donde estén (ESTUDIO_OTRAS_PAGINAS).
PAGINAS_DEL_ESTUDIO = ("editor.html", "foto.html", "media.html", "video.html")
# Lo que hace el editor de videos (Kuyuy): otro editor lo dice en vez de un «No encontrado».
_DE_VIDEOS = {"api/video-config", "api/exportar-video", "api/exportar-proyecto-video", "api/plan-video",
              "api/subtitular-video", "api/fotograma", "api/trabajo"}


def destino_de(pagina: str) -> str:
    """La carpeta donde está la página de otro editor, según ESTUDIO_OTRAS_PAGINAS ("" si no se sabe)."""
    valor = config.estudio_otras_paginas.strip()
    if "=" not in valor:
        return valor
    mapa = dict(par.split("=", 1) for par in valor.split(",") if "=" in par)
    return (mapa.get(pagina) or mapa.get("*") or "").strip()


def _otra_pagina(editor: Editor, ruta: str, peticion: Request) -> Response:
    """La página de otro editor: a donde esté, con los medios de este banco pasados a su prefijo (es el mismo banco)."""
    otras = destino_de(ruta)
    if not otras.startswith("/") or otras.startswith("//") or ".." in otras:
        return HTMLResponse(_pagina("Esta página es de otro editor del estudio.", f"El {editor.nombre.lower()} no la tiene."),
                            status_code=404, headers=_MARCO)
    otras = otras.rstrip("/") + "/"
    mio = editor.prefijo + "/"
    consulta = [(k, otras + v[len(mio):] if v.startswith(mio) else v) for k, v in parse_qsl(peticion.url.query)]
    return RedirectResponse(otras + ruta + (f"?{urlencode(consulta)}" if consulta else ""))


def _estatico(editor: Editor, ruta: str, peticion: Request) -> Response:
    """Lo estático del editor: solo sus páginas y sus carpetas (nunca el código del servidor ni otro editor)."""
    srv = servidor()
    if not any(ruta == p or (p.endswith("/") and ruta.startswith(p)) for p in editor.paginas):
        if ruta in PAGINAS_DEL_ESTUDIO:
            return _otra_pagina(editor, ruta, peticion)
        return _error("No encontrado", 404)
    if editor.carpeta is not None:
        propia = str(Path(editor.carpeta).resolve())
        destino = os.path.normpath(os.path.join(propia, ruta))
        if srv.dentro_de(propia, destino) and os.path.isfile(destino):
            return _archivo(destino)
    destino = os.path.normpath(os.path.join(srv.DIR_EDITOR, ruta))
    if not srv.dentro_de(srv.DIR_EDITOR, destino) or srv.dentro_de(srv.AQUI, destino):
        return _error("No encontrado", 404)
    return _archivo(destino)


_CARPETAS = ("miniatura/", "banco/", "plantillas/", "fuentes/", "fuentes-sistema/", "logo/", "exports/", "redes/",
             "transmisiones/", "mediateca/")


async def _get(editor: Editor, ruta: str, peticion: Request) -> Response:
    srv = servidor()
    p = editor.prefijo
    carpeta = next((c for c in _CARPETAS if ruta.startswith(c)), None)
    clave = f"GET {carpeta or ruta}"
    if carpeta is None and not ruta.startswith("api/"):
        return _estatico(editor, ruta or editor.inicio, peticion)
    if clave not in editor.rutas:
        return _error("Esto lo hace el editor de videos." if ruta in _DE_VIDEOS else "No encontrado", 404)
    rel = ruta[len(carpeta):] if carpeta else ""
    q = peticion.query_params
    if ruta == "api/health":
        salud = {"ok": True, "editor": editor.id, "banco": os.path.basename(srv.DIR_BANCO), "media": True,
                 "ffmpeg": srv._ffmpeg_disponible()}
        if em.con_mediateca():
            salud["fototeca"] = True   # «Guardar en la Fototeca» de las páginas
        return _json(salud)
    if ruta == "api/design":
        return _json(await _en_hilo(p, srv.api_design))
    if ruta == "api/logos":
        return _json([{"name": x["name"], "url": x["url"]} for x in await _en_hilo(p, srv.listar_logos)])
    if ruta == "api/fuentes":
        return _json(await _en_hilo(p, _fuentes))
    if ruta == "api/imagenes":
        # El banco del editor de piezas y, primero, las fotos de la Mediateca.
        return _json(em.fusionar(await _en_hilo(p, srv.listar_imagenes), await em.fotos_selector(p)))
    if ruta == "api/media":
        # Su banco y, primero, las fotos de la Mediateca (las copias que ya están en el banco no se repiten).
        return _json(em.fusionar(await _en_hilo(p, srv.listar_media), await em.fotos_selector(p)))
    if ruta == "api/almacen":
        return _json({"ok": True, "claves": await _en_hilo(p, srv.almacen_leer_todo)})
    if ruta == "api/video-config":
        return _json(await _en_hilo(p, srv.api_video_config))
    if ruta == "api/trabajo":
        return await _estado_trabajo(editor, q.get("id", ""))
    if ruta == "api/fotograma":
        return await _en_hilo(p, _fotograma, dict(q))
    if ruta == "api/proyectos-foto":
        return _json(await _en_hilo(p, srv.listar_proyectos, srv.DIR_PROYECTOS_FOTO))
    if ruta == "api/proyectos-media":
        return _json(await _en_hilo(p, srv.listar_proyectos, srv.DIR_PROYECTOS))
    if ruta == "api/proyecto-foto":
        return _proyecto(srv.DIR_PROYECTOS_FOTO, q.get("nombre", ""))
    if ruta == "api/proyecto-media":
        return _proyecto(srv.DIR_PROYECTOS, q.get("nombre", ""))
    fototeca = f"{em.SUBCARPETA}/"
    if carpeta == "miniatura/" and rel.startswith(fototeca) and em.con_mediateca():
        mini = await em.miniatura(rel[len(fototeca):])
        return _archivo(mini) if mini is not None else _error("Foto no encontrada.", 404)
    if carpeta == "banco/" and rel.startswith(fototeca) and em.con_mediateca():
        # Una foto de la Mediateca se materializa en el banco la primera vez que se pide.
        leido = em.leer_nombre(rel[len(fototeca):])
        if leido and not (Path(srv.DIR_BANCO) / rel).is_file():
            try:
                await em.materializar_foto(Path(srv.DIR_BANCO), leido[0])
            except em.ErrorPuente as e:
                return _error(str(e), e.codigo)
    if carpeta == "mediateca/":
        # Una pieza ya guardada en la Mediateca (el «Descargar» tras exportar).
        guardada = await em.pieza_guardada(ruta) if em.con_mediateca() else None
        return _archivo(guardada) if guardada is not None else _error("Pieza no encontrada.", 404)
    if carpeta == "miniatura/":
        return await asyncio.to_thread(_miniatura, rel)
    if carpeta == "fuentes-sistema/":
        return await asyncio.to_thread(_fuente_sistema, rel.split("/", 1)[0])
    base = {"banco/": srv.DIR_BANCO, "plantillas/": srv.DIR_PLANTILLAS, "fuentes/": srv.DIR_FUENTES,
            "logo/": srv.DIR_LOGOS, "exports/": srv.DIR_EXPORTS, "redes/": srv.DIR_REDES,
            "transmisiones/": srv.DIR_TRANSMISIONES}.get(carpeta)
    return _servir_desde(base, rel) if base else _error("No encontrado", 404)


async def _a_la_mediateca(editor: Editor, ruta: str, cuerpo: dict, sesion: dict) -> Response:
    """Lo exportado (una pieza) va SOLO a la Mediateca y el editor recibe la URL para descargarla; «Guardar en la
    Fototeca» igual, con el título y la foto de origen que manda la página."""
    pieza = sesion.get("pieza") if isinstance(sesion.get("pieza"), dict) else None
    try:
        img, ext = em.decodificar_dataurl(cuerpo.get("dataURL", ""))
    except em.ErrorPrensa as e:
        return _error(f"Datos inválidos: {e}", 400)
    if ruta == "api/fototeca-pieza":
        titulo, origen = em.datos_pieza(cuerpo)
        res = await em.ingresar_bytes(img, ext, "pieza", int(sesion["sub"]), pieza=True, titulo=titulo, origen=origen,
                                      pieza_prensa=pieza)
        return _json({"ok": True, **res}) if res else _error("No se pudo registrar en la Mediateca.", 500)
    res = await em.ingresar_bytes(img, ext, "pieza", int(sesion["sub"]), pieza=True,
                                  titulo=em.titulo_de_nombre(str(cuerpo.get("nombre") or "")),
                                  canal=str(cuerpo.get("canal") or ""), origen=em.foto_de_url(str(cuerpo.get("origen") or "")),
                                  pieza_prensa=pieza)
    if res is None:
        return _error("No se pudo guardar en la Mediateca.", 500)
    return _json({"ok": True, "url": em.url_mediateca(res["archivo"], editor.prefijo), "banco_url": "",
                  "archivo": res["archivo"].rsplit("/", 1)[-1], "fototeca": res})


# --- las imágenes del editor de piezas (Awana, E4a) ----------------------------------------------------------------


def _guardar_imagen(nombre: str, datos: bytes) -> tuple[dict, int]:
    srv = servidor()
    os.makedirs(srv.DIR_SUBIDAS, exist_ok=True)
    destino = srv.ruta_libre(os.path.join(srv.DIR_SUBIDAS, nombre))
    try:
        with open(destino, "wb") as f:
            f.write(datos)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "No se pudo guardar: %s" % e}, 500
    rel = os.path.relpath(destino, srv.DIR_BANCO)
    return {"ok": True, "name": rel.replace(os.sep, " / "), "url": srv.pub("/banco/" + "/".join(quote(s) for s in rel.split(os.sep)))}, 200


async def _imagen_subida(editor: Editor, cuerpo: dict, sesion: dict) -> Response:
    """Una imagen subida al editor de piezas ({filename, dataURL}): a su banco y, con la Mediateca, también a ella."""
    srv = servidor()
    try:
        nombre = srv.sanear_nombre(cuerpo.get("filename", "imagen.png"))
        data_url = cuerpo.get("dataURL", "")
        datos = base64.b64decode(data_url.split(",", 1)[1] if "," in data_url else data_url)
    except Exception as e:  # noqa: BLE001
        return _error("Datos inválidos: %s" % e, 400)
    respuesta, codigo = await _en_hilo(editor.prefijo, _guardar_imagen, nombre, datos)
    if codigo == 200 and em.con_mediateca():
        try:
            img, ext = em.decodificar_dataurl(data_url)
            respuesta["fototeca"] = await em.ingresar_bytes(img, ext, nombre, int(sesion["sub"]), pieza=False)
        except em.ErrorPrensa:
            pass   # una imagen que la Mediateca no admite queda solo en el banco
    return _json(respuesta, codigo)


# --- los videos (Kuyuy, E3) --------------------------------------------------------------------------------------

# Los trabajos de video pedidos desde un editor, a la espera de entrar a la Mediateca (en memoria del proceso).
_videos = em.TrabajosDeVideo()


def _fotograma(q: dict) -> Response:
    """Un fotograma de un video (o la imagen tal cual) para la línea de tiempo del editor de video."""
    srv = servidor()
    origen = srv.ruta_de_medio(q.get("origen", ""))
    if not origen:
        return _error("medio no válido", 404)
    try:
        t, alto = float(q.get("t", "0")), int(q.get("alto", "72"))
    except ValueError:
        return _error("parámetros no válidos", 400)
    if origen.lower().endswith(srv.EXTS_VIDEO):
        destino = srv.fotograma(origen, t, alto)
    else:
        destino = origen if origen.lower().endswith(srv.EXTS) else None
    return _archivo(destino, cache=destino != origen) if destino else _error("sin fotograma", 404)


async def _encolar_video(editor: Editor, ruta: str, cuerpo: dict, sesion: dict) -> Response:
    """Un trabajo de la cola de video (un ffmpeg a la vez): recortar un clip, exportar un proyecto o transcribir. Con la
    Mediateca, el video se nombra por la hora y el trabajo se anota para registrarlo cuando quede listo."""
    srv = servidor()
    if not srv._ffmpeg_disponible():
        return _error("ffmpeg no está instalado", 500)
    if ruta == "api/subtitular-video" and shutil.which("whisper") is None:
        return _error("Whisper no está instalado (pip install openai-whisper)", 500)
    if ruta == "api/exportar-proyecto-video":
        try:
            srv.montaje.normalizar(cuerpo.get("proyecto"))      # error claro antes de encolar
        except Exception as e:  # noqa: BLE001
            return _error("Datos inválidos: %s" % e, 400)
    pedido = dict(cuerpo)
    exporta = ruta != "api/subtitular-video"
    if exporta and em.con_mediateca():
        cuerpo = {**cuerpo, "nombre": em.nombre_por_hora(datetime.now(), ".mp4")}
    srv.limpiar_trabajos()
    id_trabajo = os.urandom(6).hex()
    with srv.TRABAJOS_LOCK:
        srv.TRABAJOS[id_trabajo] = {"estado": "procesando", "cola": True, "inicio": __import__("time").time(),
                                    **({} if ruta == "api/exportar-video" else {"etapa": "en cola", "progreso": 0})}
    destino = {"api/exportar-video": srv.exportar_video_en_hilo, "api/exportar-proyecto-video": srv.exportar_proyecto_en_hilo,
               "api/subtitular-video": srv.subtitular_en_hilo}[ruta]
    threading.Thread(target=destino, args=(id_trabajo, cuerpo, editor.prefijo), daemon=True).start()
    if exporta and em.con_mediateca():
        pieza = sesion.get("pieza") if isinstance(sesion.get("pieza"), dict) else None
        _videos.anotar(id_trabajo, int(sesion["sub"]), pedido, proyecto=ruta == "api/exportar-proyecto-video", pieza=pieza)
    return _json({"ok": True, "trabajo": id_trabajo})


async def _copia_temporal(editor: Editor, url: str) -> tuple[Path, str] | None:
    """El video que el editor dejó en su salida (por su URL), copiado a la carpeta temporal de la Mediateca."""
    srv = servidor()
    ruta = await _en_hilo(editor.prefijo, srv.ruta_de_medio, url)
    if not ruta or not em.ft.es_video(ruta):
        return None
    tmp = em.ft.carpeta_temporal() / f"{os.urandom(8).hex()}{Path(ruta).suffix.lower()}"
    try:
        await asyncio.to_thread(shutil.copyfile, ruta, tmp)
    except OSError:
        tmp.unlink(missing_ok=True)
        return None
    return tmp, Path(ruta).name


async def _estado_trabajo(editor: Editor, id_trabajo: str) -> Response:
    """El estado de un trabajo; si quedó listo y lo pidió este editor, el video entra a la Mediateca (una vez)."""
    srv = servidor()
    with srv.TRABAJOS_LOCK:
        t = dict(srv.TRABAJOS.get(id_trabajo, {"estado": "desconocido"}))
    if t.get("estado") == "listo" and t.get("url") and id_trabajo in _videos and em.con_mediateca():
        pendiente = _videos.tomar(id_trabajo)
        copia = await _copia_temporal(editor, str(t["url"])) if pendiente else None
        if copia:
            t["fototeca"] = await em.ingresar_ruta(copia[0], copia[1], pendiente["usuario_id"], pieza=True,
                                                   titulo=em.titulo_de_nombre(pendiente["titulo"]), canal=pendiente["canal"],
                                                   origen=pendiente.get("origen"), pieza_prensa=pendiente.get("pieza"))
    elif t.get("estado") == "error":
        _videos.tomar(id_trabajo)
    return _json(t)


async def _video_a_la_mediateca(editor: Editor, cuerpo: dict, sesion: dict) -> Response:
    """«Guardar en la Fototeca» del editor de video: la puerta explícita (y el reintento); por la huella, nunca duplica."""
    if not em.con_mediateca():
        return _error("Sin Mediateca: el video queda en la salida del editor.", 404)
    copia = await _copia_temporal(editor, str(cuerpo.get("url") or ""))
    if copia is None:
        return _error("No se encontró ese video en el editor.", 400)
    pieza = sesion.get("pieza") if isinstance(sesion.get("pieza"), dict) else None
    res = await em.ingresar_ruta(copia[0], copia[1], int(sesion["sub"]), pieza=True,
                                 titulo=em.titulo_de_nombre(str(cuerpo.get("titulo") or "")),
                                 canal=str(cuerpo.get("canal") or ""), pieza_prensa=pieza)
    if res is None:
        return _error("No se pudo registrar en la Mediateca.", 500)
    return _json({"ok": True, "numero": res["id"], **res})


async def _post(editor: Editor, ruta: str, peticion: Request, sesion: dict) -> Response:
    srv = servidor()
    if f"POST {ruta}" not in editor.rutas:
        return _error("Esto lo hace el editor de videos." if ruta in _DE_VIDEOS else "No encontrado", 404)
    if ruta == "api/subir":
        return await _subir(peticion, editor, sesion)
    try:
        cuerpo = await _cuerpo_json(peticion, srv.MAX_JSON) if ruta in _POST_JSON else {}
    except HTTPException as e:
        return _error(e.detail, e.status_code)
    if ruta in ("api/exportar-foto", "api/fototeca-pieza") and em.con_mediateca():
        return await _a_la_mediateca(editor, ruta, cuerpo, sesion)
    if ruta in ("api/exportar-video", "api/exportar-proyecto-video", "api/subtitular-video"):
        return await _encolar_video(editor, ruta, cuerpo, sesion)
    if ruta == "api/plan-video":
        try:
            plan = await _en_hilo(editor.prefijo, srv.plan_video_wasm, cuerpo.get("proyecto"), cuerpo.get("normalizar", True) is not False)
        except Exception as e:  # noqa: BLE001 — como el servidor del estudio: el error, al editor
            return _error("No se pudo preparar: %s" % e, 400)
        return _json(plan)
    if ruta == "api/fototeca-video":
        return await _video_a_la_mediateca(editor, cuerpo, sesion)
    if ruta == "api/fototeca-pieza":
        return _error("Sin Mediateca: la pieza se descarga o se guarda en la salida.", 404)
    if ruta == "api/imagenes":
        return await _imagen_subida(editor, cuerpo, sesion)
    funcion = {"api/almacen": _guardar_almacen, "api/exportar-foto": _exportar_foto, "api/analizar-foto": _analizar,
               "api/mejorar-foto": _mejorar}.get(ruta)
    if ruta == "api/proyecto-foto":
        datos, codigo = await _en_hilo(editor.prefijo, _guardar_proyecto, srv.DIR_PROYECTOS_FOTO, cuerpo)
    elif ruta == "api/proyecto-media":
        datos, codigo = await _en_hilo(editor.prefijo, _guardar_proyecto, srv.DIR_PROYECTOS, cuerpo)
    elif funcion is not None:
        datos, codigo = await _en_hilo(editor.prefijo, funcion, cuerpo)
    else:
        return _error("No encontrado", 404)
    return _json(datos, codigo)


# Las carpetas del editor SOLO (su perfil): las que el perfil del estudio reparte.
CARPETAS_SOLO = {"banco": "banco", "almacen": "almacen", "proyectos_foto": "proyectos-foto", "proyectos_media": "proyectos-media",
                 "exports": "trabajo", "redes": "salida/redes", "transmisiones": "salida/transmisiones"}


def perfil_propio(carpeta: Path, editor: str) -> Path:
    """<carpeta>/perfil.json con sus carpetas dentro de `carpeta` (si ya está, no se toca): el perfil de un editor solo."""
    perfil = carpeta / "perfil.json"
    if not perfil.is_file():
        carpeta.mkdir(parents=True, exist_ok=True)
        rutas = {k: str(carpeta / v) for k, v in CARPETAS_SOLO.items()}
        perfil.write_text(json.dumps({"_": f"perfil del {editor} solo", "rutas": rutas}, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return perfil


class SesionEditor(BaseModel):
    # La pieza de prensa para la que se abre el editor (Prensa → Piezas → «Hacer la pieza gráfica»).
    pieza: int | None = None


def crear_router(editor: Editor) -> APIRouter:
    """Las rutas de un editor: su sesión (con la ficha de la API) y, con su cookie, sus páginas y su API."""
    router = APIRouter(tags=[editor.id])

    @router.post(f"{editor.prefijo}/sesion")
    async def abrir_sesion(peticion: Request, datos: SesionEditor | None = None,
                           usuario: Usuario = Depends(usuario_actual)) -> Response:
        """La cookie del editor para su marco; la página que lo muestra la renueva mientras sigue abierta. Con
        `pieza`, lo exportado queda vinculado a esa pieza de prensa."""
        if getattr(usuario, "rol", "invitado") == "invitado":
            raise HTTPException(403, f"La cuenta de invitado solo puede consultar: el {editor.nombre.lower()} es para hacer piezas.")
        pieza = await pieza_de(datos.pieza if datos else None)
        if datos and datos.pieza and pieza is None and _hay_piezas():
            raise HTTPException(404, "Pieza de prensa no encontrada.")
        valor, vence = firmar_sesion(editor, usuario.id, usuario.rol, pieza)
        # La caché de los editores en la Mediateca se limpia sola al abrir uno (antes, al abrir el estudio aparte).
        await em.limpiar_cache(usuario.id)
        # Secure solo si el navegador llegó por https (enlace público): en la red local la web va por http.
        seguro = peticion.headers.get("x-forwarded-proto", peticion.url.scheme).split(",")[0].strip() == "https"
        r = JSONResponse({"ok": True, "estudio": True, "banco": em.con_mediateca(), "pieza": pieza,
                          "pagina": f"{editor.prefijo}/{editor.inicio}", "vence": vence.isoformat()},
                         headers={"Cache-Control": "no-store"})
        r.set_cookie(editor.cookie, valor, max_age=MINUTOS_SESION * 60, path=editor.prefijo, httponly=True,
                     samesite="strict", secure=seguro)
        return r

    @router.post(f"{editor.prefijo}/traer/{{foto_id}}")
    async def traer(foto_id: int, usuario: Usuario = Depends(usuario_actual)) -> dict:
        """«Usar en Prensa» de la Mediateca: la foto (con sus ajustes) queda en el banco del editor; devuelve su URL."""
        if getattr(usuario, "rol", "invitado") == "invitado":
            raise HTTPException(403, "La cuenta de invitado solo puede consultar.")
        if not em.con_mediateca():
            raise HTTPException(404, "Sin Mediateca.")
        try:
            foto, nombre = await em.materializar_foto(Path(servidor().DIR_BANCO), foto_id)
        except em.ErrorPuente as e:
            raise HTTPException(e.codigo, str(e))
        return {"ok": True, "url": em.url_banco(nombre, editor.prefijo), "nombre": foto["titulo"] or foto["nombre_original"]}

    @router.delete(f"{editor.prefijo}/sesion")
    async def cerrar_sesion() -> Response:
        """Borra la cookie del editor (al cerrar sesión en la web). Sin ficha: solo borra."""
        r = JSONResponse({"ok": True})
        r.delete_cookie(editor.cookie, path=editor.prefijo, httponly=True, samesite="strict")
        return r

    @router.get(editor.prefijo, include_in_schema=False)
    async def inicio() -> Response:
        return RedirectResponse(f"{editor.prefijo}/{editor.inicio}")

    @router.api_route(f"{editor.prefijo}/{{ruta:path}}", methods=["GET", "HEAD", "POST"], include_in_schema=False)
    async def editor_(ruta: str, peticion: Request) -> Response:
        # Lo protege la cookie del editor (el marco no manda la ficha de la API).
        sesion = leer_sesion(editor, peticion.cookies.get(editor.cookie))
        if sesion is None:
            return _sin_sesion(peticion, editor)
        limpia = ruta_segura(ruta)
        if limpia is None:
            return _error("Ruta no válida.", 404)
        if peticion.method == "POST":
            return await _post(editor, limpia, peticion, sesion)
        return await _get(editor, limpia, peticion)

    return router
