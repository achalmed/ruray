"""ruray/mediateca.py — el puente de los editores del estudio con la Mediateca (editores E2b, fase 10.2b,
2026-10-20). Es parte de la base común de los editores (ruray/comun.py).

La Mediateca es la ÚNICA biblioteca de fotos. Un editor la usa solo por «medios.v2», y solo si el anfitrión la ofrece
(solo, sin Mediateca, el editor trabaja con su banco y su salida, como antes):

- el SELECTOR del editor (`api/media`) recibe, además de su banco, las fotos públicas y las del álbum «Prensa»;
- una foto de la Mediateca aparece como un archivo de su banco (`<banco>/fototeca/ft-<id>-<versión>.jpg`, el derivado
  con sus ajustes): se materializa al pedirla, y su miniatura sale de la Mediateca;
- lo que el editor EXPORTA se guarda solo en la Mediateca (ámbito «prensa», nombre por la fecha, formato y red como
  etiquetas, versión de su foto de origen, vinculado a la pieza de prensa para la que se abrió) y se descarga desde ahí;
  lo que se SUBE al editor también entra (ámbito «actividad», etiqueta «Prensa»).

Lo puro (nombres, metadatos, dataURL) y la limpieza de la caché vinieron de `servicios/prensa.py` y de su proxy
`/estudio/`, que E5 retiró (2026-10-21).
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

from tiqsi.modulo import Perezosa, hay

# La Mediateca por el contrato: «medios.v2» (sin sus modelos), pedida al anfitrión al usarla; nada se importa de ella.
ft = Perezosa("medios.v2")

log = logging.getLogger("qillqa.estudio")

SUBCARPETA = "fototeca"
# Tamaño del derivado que recibe el editor (los PRESETS de la Mediateca): el original con sus ajustes.
PRESET = "original"
ALBUM_PRENSA = "Prensa"
ETIQUETA_PIEZA = "Pieza de prensa"
ETIQUETA_SUBIDA = "Prensa"
LIMITE_FOTOS = 300

_NOMBRE_RE = re.compile(r"^ft-(\d{1,10})-([0-9a-f]{1,12})\.jpg$")
_EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}


class ErrorPrensa(RuntimeError):
    pass


def con_mediateca() -> bool:
    """¿El anfitrión ofrece la Mediateca? Solo, sin ella, el editor usa su banco y su salida."""
    try:
        return hay("medios.v2")
    except RuntimeError:   # sin anfitrión activo (una prueba que monta solo el router)
        return False


# --- las fotos de la Mediateca en el banco del editor ----------------------------------------------------------------


def nombre_derivado(foto_id: int, version: str) -> str:
    return f"ft-{int(foto_id)}-{version}.jpg"


def leer_nombre(nombre: str) -> tuple[int, str] | None:
    """«ft-12-0.jpg» → (12, '0'); cualquier otro nombre → None."""
    m = _NOMBRE_RE.match(nombre or "")
    return (int(m.group(1)), m.group(2)) if m else None


def url_banco(nombre: str, prefijo: str) -> str:
    """La URL con que el navegador pide una foto de la Mediateca al banco del editor."""
    return f"{prefijo}/banco/{SUBCARPETA}/{nombre}"


def foto_de_url(url: str) -> int | None:
    """El id de la Mediateca de una URL del banco del editor (con cualquier prefijo delante)."""
    url = unquote((url or "").split("?", 1)[0])
    if f"/banco/{SUBCARPETA}/" not in url:
        return None
    leido = leer_nombre(url.rsplit("/", 1)[-1])
    return leido[0] if leido else None


def materializar(banco: Path, foto_id: int, archivo: str, sha: str, ajustes: dict | None) -> Path:
    """Deja en `<banco>/fototeca/` el derivado de la foto (con sus ajustes) y devuelve su ruta.

    Idempotente: el nombre lleva la versión de los ajustes; si ya está, no se rehace. Corre en un hilo (Pillow)."""
    nombre = nombre_derivado(foto_id, ft.clave_ajustes(ajustes))
    destino = banco / SUBCARPETA / nombre
    if destino.is_file():
        return destino
    origen = ft.exportar(archivo, sha, ajustes, PRESET, "jpg")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(f".{nombre}.{uuid.uuid4().hex[:8]}.tmp")
    shutil.copyfile(origen, tmp)
    tmp.replace(destino)
    return destino


def item_foto(foto: dict, prefijo: str) -> dict:
    """Una foto de la Mediateca como la lista el selector del editor ({name, url, credito, carpeta})."""
    titulo = foto.get("titulo") or Path(foto.get("nombre_original") or f"foto-{foto['id']}").stem
    return {
        "name": " / ".join(p for p in ("Fototeca", foto.get("album") or "Sin álbum", f"{titulo} (n.º {foto['id']})") if p),
        "url": url_banco(nombre_derivado(foto["id"], foto["version"]), prefijo),
        "credito": "",
        "carpeta": "Fototeca",
    }


def _sin_copias(items: list) -> list:
    """Quita del listado del editor las copias de la Mediateca que ya están en su banco: el selector las ofrece desde
    la Mediateca, con la versión vigente de sus ajustes."""
    marca = f"/banco/{SUBCARPETA}/"
    return [i for i in items if not (isinstance(i, dict) and marca in str(i.get("url", "")))]


def fusionar(listado, fotos: list[dict]):
    """Junta el listado del editor (/api/imagenes: lista; /api/media: {imagenes, videos}) con las fotos de la
    Mediateca, que van primero."""
    if isinstance(listado, list):
        return fotos + _sin_copias(listado)
    if isinstance(listado, dict) and isinstance(listado.get("imagenes"), list):
        return {**listado, "imagenes": fotos + _sin_copias(listado["imagenes"])}
    return listado


# --- lo que vuelve del editor ----------------------------------------------------------------------------------------


def decodificar_dataurl(data_url: str) -> tuple[bytes, str]:
    """(bytes, extensión) de un «data:image/png;base64,…». Falla si no es una imagen."""
    if not isinstance(data_url, str) or "," not in data_url:
        raise ErrorPrensa("No es una imagen en dataURL.")
    cabecera, b64 = data_url.split(",", 1)
    tipo = cabecera[5:].split(";", 1)[0].lower() if cabecera.startswith("data:") else ""
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp"}.get(tipo)
    if ext is None:
        raise ErrorPrensa(f"Formato no admitido: {tipo or 'desconocido'}.")
    try:
        datos = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        raise ErrorPrensa("La imagen no se pudo leer.")
    if not datos:
        raise ErrorPrensa("La imagen está vacía.")
    return datos, ext


def es_imagen(nombre: str) -> bool:
    return Path(nombre or "").suffix.lower() in _EXT_IMAGEN


def datos_pieza(pedido: dict) -> tuple[str, int | None]:
    """(título, foto de origen) de «Guardar en la Fototeca».

    El título es el nombre de la edición (plantilla y fecha); la foto de origen, la primera que se reconozca: por la
    URL del banco (`/banco/fototeca/ft-N-…`) o por el «n.º N» que el selector pone en el nombre de la capa."""
    titulo = " ".join(str(pedido.get("titulo") or "").split())[:200] or "Pieza de prensa"
    for url in pedido.get("origenes") or []:
        foto = foto_de_url(str(url))
        if foto:
            return titulo, foto
    for n in pedido.get("fotos") or []:
        if isinstance(n, int) and not isinstance(n, bool) and n > 0:
            return titulo, n
    return titulo, None


# --- las piezas en la Mediateca (2026-10-20) --------------------------------------------------------------------------
# Edison: «los resultados del módulo de prensa deben guardarse en su carpeta de mediateca»; «todos los archivos deben
# tener únicamente fechas como nombres»; lo descriptivo, en etiquetas y metadatos. Cada pieza exportada es un registro
# de ámbito «prensa»: nombre AAAA/AAAAMMDD_HHMMSS.ext por la fecha de exportación, su formato en `categoria`, etiquetas
# del formato y de la red y, si sale de una foto de la Mediateca, una versión de ella (tipo «exportacion»).

AMBITO = "prensa"
FORMATOS = ("post", "historia", "portada", "video")
ETIQUETA_FORMATO = {"post": "Post", "historia": "Historia", "portada": "Portada", "video": "Video"}
# Los canales del estudio con su nombre de red.
REDES = {"facebook": "Facebook", "instagram": "Instagram", "tiktok": "TikTok", "estados": "Estados de WhatsApp",
         "x": "X", "youtube": "YouTube", "linkedin": "LinkedIn", "transmisiones": "Transmisión"}
TIPO_VERSION = "exportacion"
TIPO_USO = "prensa"


def red_de(canal: str) -> str:
    """La clave de la red de un canal del estudio («Facebook» → «facebook»), o "" si no es una."""
    c = re.sub(r"[^a-z]", "", (canal or "").lower())
    return c if c in REDES else ""


def formato_pieza(ancho: int, alto: int, medio: str = "foto") -> str:
    """El formato por la proporción: vertical 9:16 → historia; apaisada (16:9, 1,91:1, portada de página) → portada;
    cuadrada o 4:5 → post. Un video es «video» sea cual sea su forma."""
    if medio == "video":
        return "video"
    if not ancho or not alto:
        return "post"
    r = alto / ancho
    if r >= 1.5:
        return "historia"
    if r <= 0.6:
        return "portada"
    return "post"


def titulo_de_nombre(nombre: str) -> str:
    """El título legible de lo que el editor llamó su archivo («2026-08-08-convocatoria-8ago-post.png» → «Convocatoria
    8ago post»): sin extensión, sin la fecha delante y sin guiones."""
    base = Path(nombre or "").name
    base = base.rsplit(".", 1)[0] if "." in base else base
    base = re.sub(r"^\d{4}-\d{2}-\d{2}[-_ ]*", "", base)
    base = " ".join(re.sub(r"[-_]+", " ", base).split())[:200]
    return base[:1].upper() + base[1:] if base else ""


def metadatos_pieza(*, canal: str, medio: str, ancho: int, alto: int, titulo: str = "",
                    foto_origen: int | None = None, pieza: dict | None = None) -> dict:
    """Lo que la Mediateca guarda de una pieza nueva: ámbito, formato (categoría), etiquetas, título y descripción.
    `pieza` es la pieza de prensa para la que se hizo ({id, titular})."""
    formato = formato_pieza(ancho, alto, medio)
    red = red_de(canal)
    etiquetas = [ETIQUETA_PIEZA, ETIQUETA_FORMATO[formato]] + ([REDES[red]] if red else [])
    titular = " ".join(str((pieza or {}).get("titular") or "").split())
    descripcion = "Video hecho en el estudio de Prensa" if medio == "video" else "Pieza hecha en el estudio de Prensa"
    if red:
        descripcion += f" para {REDES[red]}"
    if foto_origen:
        descripcion += f", con la foto n.º {foto_origen} de la Mediateca"
    descripcion += "."
    if titular:
        descripcion += f" Para la pieza de prensa «{titular}»."
    return {"ambito": AMBITO, "categoria": formato, "etiquetas": etiquetas,
            "titulo": (titulo or titular or ETIQUETA_FORMATO[formato])[:300], "descripcion": descripcion}


def usos_pieza(canal: str, pieza: dict | None) -> list[str]:
    """Las referencias de uso (tipo «prensa») de una pieza y de su foto de origen: la red para la que se hizo y la pieza
    de prensa, si se hizo para una."""
    refs = []
    if red_de(canal):
        refs.append(f"red:{red_de(canal)}")
    if pieza and isinstance(pieza.get("id"), int):
        refs.append(f"pieza:{pieza['id']}")
    return refs


def ruta_mediateca(limpia: str) -> str | None:
    """La ruta relativa a la Mediateca de una pieza pedida por el editor («mediateca/2026/20261020_103015.png» →
    «2026/20261020_103015.png»); solo nombres por fecha, nunca la caché ni la marca."""
    if not limpia.startswith("mediateca/"):
        return None
    rel = limpia[len("mediateca/"):]
    return rel if re.fullmatch(r"\d{4}/\d{8}_\d{6}(_\d+)?\.[a-z0-9]{2,5}", rel) else None


def url_mediateca(archivo: str, prefijo: str) -> str:
    """URL (bajo el editor, con su cookie) con la que el editor descarga una pieza ya guardada."""
    return f"{prefijo}/mediateca/{archivo}"


# --- el puente, por «medios.v2» -----------------------------------------------------------------------------------


class ErrorPuente(RuntimeError):
    def __init__(self, codigo: int, texto: str) -> None:
        super().__init__(texto)
        self.codigo = codigo


async def fotos_selector(prefijo: str, limite: int = LIMITE_FOTOS) -> list[dict]:
    """Lo que el selector del editor recibe de la Mediateca (nada si no está)."""
    if not con_mediateca():
        return []
    return [item_foto(f, prefijo) for f in await ft.fotos_para_editor(ALBUM_PRENSA, limite)]


async def materializar_foto(banco: Path | None, foto_id: int) -> tuple[dict, str]:
    """La foto de la Mediateca en el banco del editor. → (la foto, el nombre en el banco). ErrorPuente si no se puede."""
    if banco is None:
        raise ErrorPuente(503, "Falta el banco del editor: defina IDENTIDAD_PERFIL (o ESTUDIO_BANCO).")
    foto = await ft.foto_vigente(foto_id)
    if foto is None:
        raise ErrorPuente(404, "Foto no encontrada.")
    if foto["medio"] == "video":
        raise ErrorPuente(422, "Es un video: el editor recibe fotos de la Mediateca.")
    try:
        ruta = await asyncio.to_thread(materializar, banco, foto["id"], foto["archivo"], foto["sha256"], foto["ajustes"])
    except ft.ErrorFototeca as e:
        raise ErrorPuente(422, str(e))
    except FileNotFoundError:
        raise ErrorPuente(404, "El original no está en la Mediateca.")
    except OSError as e:
        raise ErrorPuente(503, f"No se pudo escribir en el banco del editor: {e.strerror or e}.")
    return foto, ruta.name


async def miniatura(nombre: str) -> Path | None:
    """La miniatura de una foto de la Mediateca, por su nombre en el banco («ft-12-0.jpg»), o None."""
    leido = leer_nombre(nombre)
    foto = await ft.foto_vigente(leido[0]) if leido else None
    if foto is None:
        return None
    try:
        return await asyncio.to_thread(ft.derivado, foto["archivo"], foto["sha256"], foto["ajustes"], "miniatura")
    except (ft.ErrorFototeca, FileNotFoundError):
        return None


async def pieza_guardada(limpia: str) -> Path | None:
    """El archivo de una pieza ya guardada en la Mediateca («mediateca/AAAA/…»), solo de Prensa, o None."""
    rel = ruta_mediateca(limpia)
    pieza = await ft.pieza_vigente(rel, AMBITO) if rel else None
    if pieza is None:
        return None
    try:
        ruta = ft.ruta_original(pieza["archivo"])
    except ft.ErrorFototeca:
        return None
    return ruta if ruta.is_file() else None


async def ingresar_ruta(tmp: Path, nombre: str, usuario_id: int | None, *, pieza: bool, titulo: str = "",
                        canal: str = "", origen: int | None = None, pieza_prensa: dict | None = None) -> dict | None:
    """Lo que vino del editor, ya en la carpeta temporal de la Mediateca, entra a ella (se mueve o se borra). Una PIEZA
    con los metadatos de Prensa; una imagen SUBIDA, como foto más con la etiqueta «Prensa». → {id, nueva, archivo}."""
    if pieza:
        def metadatos(medio: str, ancho: int, alto: int) -> dict:
            return metadatos_pieza(canal=canal, medio=medio, ancho=ancho, alto=alto, titulo=titulo,
                                   foto_origen=origen, pieza=pieza_prensa)

        return await ft.ingresar(tmp, nombre, usuario_id, metadatos=metadatos, usos=usos_pieza(canal, pieza_prensa),
                                 tipo_uso=TIPO_USO, origen=origen, tipo_version=TIPO_VERSION)
    return await ft.ingresar(tmp, nombre, usuario_id, etiquetas=[ETIQUETA_SUBIDA], titulo=titulo)


async def ingresar_bytes(datos: bytes, ext: str, nombre: str, usuario_id: int | None, **extra) -> dict | None:
    """Lo mismo, desde los bytes (una imagen en dataURL o una subida)."""
    tmp = ft.carpeta_temporal() / f"{uuid.uuid4().hex}{ext}"
    try:
        await asyncio.to_thread(tmp.write_bytes, datos)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        log.warning("No se pudo registrar en la Mediateca lo que vino de un editor (%s): %s", nombre, e)
        return None
    return await ingresar_ruta(tmp, nombre, usuario_id, **extra)


# --- los videos que exporta un editor (trabajos en segundo plano) -------------------------------------------------
# Un video exportado es un trabajo de la cola de video: se anota quién lo pidió y para qué y, cuando queda listo, entra a
# la Mediateca una sola vez. El editor lo deja antes en su salida (la caché de la Mediateca, por el perfil) con un nombre
# solo de fecha y hora: el nombre que se escribió viaja como título, no como nombre de archivo.

# Un trabajo que nadie consultó en este tiempo se olvida (la pieza queda en su canal).
HORAS_TRABAJO = 12

class TrabajosDeVideo:
    """Los trabajos de video pedidos por el proxy, a la espera de quedar listos: trabajo →
    {usuario_id, canal, titulo, proyecto, desde}. Vive en memoria de la API (un reinicio
    los olvida: la pieza sigue en su canal y se puede subir a mano)."""

    def __init__(self) -> None:
        self._pend: dict[str, dict] = {}

    def anotar(self, trabajo: str, usuario_id: int, pedido: dict, proyecto: bool,
               ahora: datetime | None = None, pieza: dict | None = None) -> None:
        ahora = ahora or datetime.now(timezone.utc)
        self._olvidar_viejos(ahora)
        titulo = " ".join(str(pedido.get("nombre") or "").split())[:200]
        self._pend[str(trabajo)] = {"usuario_id": usuario_id, "canal": str(pedido.get("canal") or ""),
                                    "titulo": titulo, "proyecto": proyecto, "desde": ahora,
                                    # La foto de la Mediateca de la que sale (solo el editor de medios: un clip).
                                    "origen": None if proyecto else foto_de_url(str(pedido.get("origen") or "")),
                                    "pieza": pieza}

    def tomar(self, trabajo: str) -> dict | None:
        """Lo pendiente de un trabajo, una sola vez (dos consultas simultáneas no lo registran dos veces)."""
        return self._pend.pop(str(trabajo), None)

    def devolver(self, trabajo: str, datos: dict) -> None:
        self._pend[str(trabajo)] = datos

    def _olvidar_viejos(self, ahora: datetime) -> None:
        limite = ahora - timedelta(hours=HORAS_TRABAJO)
        for k in [k for k, v in self._pend.items() if v["desde"] < limite]:
            self._pend.pop(k, None)

    def __contains__(self, trabajo: str) -> bool:
        return str(trabajo) in self._pend

def nombre_por_hora(momento: datetime, ext: str) -> str:
    """El nombre con que el estudio deja un video en su salida: solo la hora («103015.mp4»); el
    estudio le antepone la fecha («2026-10-20-103015.mp4»). Nada descriptivo en un nombre."""
    return f"{momento:%H%M%S}{ext if ext.startswith('.') else '.' + ext}"


# --- la caché de los editores en la Mediateca (antes, del proxy /estudio/; E5) --------------------------------------
# Las rutas `redes`, `transmisiones` y `exports` del perfil apuntan a `<Mediateca>/cache/prensa`: «salida» es donde un
# editor deja un video mientras entra a la Mediateca (y de donde se descarga un rato); «trabajo», sus temporales,
# miniaturas y fotos mejoradas. Todo es regenerable y se limpia solo por antigüedad al abrir un editor.
CACHE = Path("cache") / "prensa"
HORAS_CACHE = {"salida": 48, "trabajo": 14 * 24}
# Se limpia a lo sumo una vez cada tanto (Prensa abre las sesiones de los tres editores a la vez).
MINUTOS_ENTRE_LIMPIEZAS = 10
_limpieza = {"ultima": 0.0}
_candado_limpieza = asyncio.Lock()


def vencidos(raiz: Path, ahora: float | None = None) -> dict[str, list[Path]]:
    """Lo de `<raiz>/cache/prensa/{salida,trabajo}` más viejo que `HORAS_CACHE`, por carpeta. Nunca sale de esa carpeta
    (no sigue enlaces) ni toca lo demás de la caché. Lo de «salida» que aún no esté en la Mediateca se registra antes de
    borrarlo (`limpiar_cache`): un video cuyo trabajo nadie consultó (pestaña cerrada, API reiniciada) no se pierde."""
    import time

    ahora = time.time() if ahora is None else ahora
    base = (raiz / CACHE).resolve()
    salida: dict[str, list[Path]] = {}
    for sub, horas in HORAS_CACHE.items():
        salida[sub] = []
        carpeta = base / sub
        if not carpeta.is_dir():
            continue
        limite = ahora - horas * 3600
        for ruta in sorted(carpeta.rglob("*")):
            try:
                if ruta.is_symlink() or not ruta.is_file() or base not in ruta.resolve().parents:
                    continue
                if ruta.stat().st_mtime < limite:
                    salida[sub].append(ruta)
            except OSError:
                continue
    return salida


def canal_de_salida(raiz: Path, ruta: Path) -> str:
    """El canal de un archivo de la salida por su carpeta («…/salida/redes/facebook/x.mp4» → «facebook»;
    «…/salida/transmisiones/x.mp4» → «transmisiones»); "" si no se reconoce."""
    try:
        partes = ruta.resolve().relative_to((raiz / CACHE / "salida").resolve()).parts
    except ValueError:
        return ""
    if len(partes) >= 2 and partes[0] == "transmisiones":
        return "transmisiones"
    if len(partes) >= 3 and partes[0] == "redes":
        return red_de(partes[1])
    return ""


async def limpiar_cache(usuario_id: int, ahora: float | None = None) -> None:
    """Borra lo vencido de la caché. Lo de la salida que aún no está en la Mediateca se registra antes como pieza (por su
    huella, nunca dos veces); si el registro falla, queda para la próxima. Nada de esto impide abrir un editor."""
    import time

    if not con_mediateca():
        return
    ahora = time.time() if ahora is None else ahora
    async with _candado_limpieza:
        if ahora - _limpieza["ultima"] < MINUTOS_ENTRE_LIMPIEZAS * 60:
            return
        _limpieza["ultima"] = ahora
        try:
            lista = await asyncio.to_thread(vencidos, ft.raiz())
            for ruta in lista["salida"]:
                if ft.admitido(ruta) or ft.es_video(ruta):
                    tmp = ft.carpeta_temporal() / f"{uuid.uuid4().hex}{ruta.suffix.lower()}"
                    await asyncio.to_thread(shutil.copyfile, ruta, tmp)
                    if await ingresar_ruta(tmp, ruta.name, usuario_id, pieza=True,
                                           canal=canal_de_salida(ft.raiz(), ruta)) is None:
                        continue
                ruta.unlink(missing_ok=True)
            for ruta in lista["trabajo"]:
                ruta.unlink(missing_ok=True)
        except OSError as e:
            log.warning("No se pudo limpiar la caché de los editores: %s", e)
