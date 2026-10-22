#!/usr/bin/env python3
"""editor/mejorar_foto.py — mejora automática de una foto (nivel, contraste, nitidez) antes de embeberla o publicarla."""
# ============================================================
# MEJORAR-FOTO — realce automático y NATURAL de fotos de baja calidad.
#
# Pensado para fotos que llegan por WhatsApp (comprimidas, pixeladas, con
# ruido y poca resolución): las deja limpias y nítidas para publicar en redes
# sin que se vean pixeladas, SIN que parezcan "hechas por IA". No hay
# alucinación de detalle: es procesamiento clásico avanzado (deblock → denoise
# → upscale Lanczos → sharpen → contraste local suave → color), moderado.
#
# Uso:
#   python3 mejorar_foto.py --analizar <img>              # -> JSON de calidad
#   python3 mejorar_foto.py <entrada> <salida> [opciones] # -> escribe la mejora
#
# Opciones (todas 0..100; -1 = automático según el análisis):
#   --nivel suave|auto|intensiva   intensidad global (por defecto: auto)
#   --nitidez N  --ruido N  --claridad N  --contraste N  --color N
#   --luz N      --resolucion N    (N = objetivo del lado largo en px, o -1 auto)
#   --formato jpg|png|webp   (por defecto: conserva; jpg si no aplica)
#
# NO destructivo: nunca toca la entrada; solo escribe la salida.
# Requiere: Pillow (obligatorio). scikit-image + scipy si están (mejor
# resultado); si faltan, cae a un modo PIL puro que también mejora.
# ============================================================
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # raíz del repo: lib/nucleo
from lib import nucleo  # noqa: E402  raíz y logger de core/ (RQ-COD-06)

log = nucleo.registro("identidad-visual.mejorar_foto")

# scikit-image / scipy son OPCIONALES: si están, el realce es mejor (denoise
# que respeta bordes, contraste local CLAHE, estimación de ruido). Si no, se
# usa un camino PIL puro (autocontraste + unsharp + Lanczos), que igual sirve.
try:
    from skimage import restoration, exposure
    from scipy import ndimage as ndi
    _SK = True
except Exception:
    _SK = False

# Tope del lado largo de salida: suficiente para 1080 de redes + recorte, sin
# reventar la RAM (equipos del despacho pueden ir justos de memoria).
MAX_LADO = 2048
# Perfiles de intensidad global. Cada efecto se multiplica por esto.
NIVELES = {"suave": 0.55, "auto": 1.0, "intensiva": 1.7}


# --------------------------------------------------------------- utilidades
def _cargar(ruta):
    """Abre respetando la orientación EXIF y devuelve RGB float32 [0,1]."""
    im = Image.open(ruta)
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGB")
    arr = np.asarray(im, dtype=np.float32) / 255.0
    return im, arr


def _lum(arr):
    """Luminancia perceptual (Rec.709)."""
    return arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722


def _blockiness(Y):
    """Proxy de artefactos de bloque JPEG: energía en los bordes de bloque 8x8
    frente a la energía media. >~1.2 sugiere compresión visible (WhatsApp)."""
    if Y.shape[1] < 16 or Y.shape[0] < 16:
        return 0.0
    dh = np.abs(np.diff(Y, axis=1))
    dv = np.abs(np.diff(Y, axis=0))
    borde = (dh[:, 7::8].mean() + dv[7::8, :].mean()) / 2.0
    interior = (dh.mean() + dv.mean()) / 2.0 + 1e-6
    return float(borde / interior)


def _sharpness(Y):
    """Varianza del laplaciano (nitidez). Bajo = foto borrosa/blanda."""
    if _SK:
        lap = ndi.laplace(Y.astype(np.float32))
    else:
        # laplaciano simple sin scipy
        lap = (-4 * Y
               + np.roll(Y, 1, 0) + np.roll(Y, -1, 0)
               + np.roll(Y, 1, 1) + np.roll(Y, -1, 1))
    return float(lap.var())


def _sigma_ruido(arr):
    if _SK:
        try:
            s = restoration.estimate_sigma(arr, channel_axis=-1, average_sigmas=True)
            return float(s)
        except Exception:
            pass
    # estimación tosca: desviación del detalle de alta frecuencia de la luminancia
    Y = _lum(arr)
    hp = Y - ndi.gaussian_filter(Y, 1.0) if _SK else Y - np.asarray(
        Image.fromarray((Y * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(1)),
        dtype=np.float32) / 255.0
    return float(hp.std())


def analizar(ruta):
    """Métricas de calidad + veredicto (¿necesita mejora y por qué?)."""
    im, arr = _cargar(ruta)
    w, h = im.size
    lado = max(w, h)
    Y = _lum(arr)
    sigma = _sigma_ruido(arr)
    block = _blockiness(Y)
    sharp = _sharpness(Y)
    try:
        tam_kb = round(os.path.getsize(ruta) / 1024)
    except OSError:
        tam_kb = None

    motivos = []
    if lado < 1080:
        motivos.append("resolución muy baja")
    elif lado < 1400:
        motivos.append("resolución reducida")
    if block > 1.28:
        motivos.append("artefactos de compresión")
    if sigma > 0.020:
        motivos.append("ruido")
    if sharp < 0.00060:
        motivos.append("poca nitidez")

    necesita = bool(motivos)
    # etiqueta corta para la interfaz
    if lado < 1080 or block > 1.5:
        etiqueta = "Calidad baja"
    elif necesita:
        etiqueta = "Calidad media"
    else:
        etiqueta = "Buena calidad"

    return {
        "ok": True, "w": w, "h": h, "lado": lado,
        "mpx": round(w * h / 1e6, 2), "tam_kb": tam_kb,
        "sigma": round(sigma, 4), "blockiness": round(block, 3),
        "nitidez": round(sharp, 5),
        "necesita": necesita, "etiqueta": etiqueta,
        "motivo": ", ".join(motivos) if motivos else "sin problemas evidentes",
    }


# ------------------------------------------------------------------ realce
def _slider(v, base, k):
    """Convierte una opción 0..100 (o -1=auto) en un factor de fuerza.
    -1 => base*k (automático). 0 => desactivado. 50 => base. 100 => base*2."""
    if v is None or v < 0:
        return base * k
    return base * (v / 50.0)


def mejorar(entrada, salida, nivel="auto", nitidez=-1, ruido=-1, claridad=-1,
            contraste=-1, color=-1, luz=-1, resolucion=-1, formato=None):
    k = NIVELES.get(nivel, 1.0)
    im, arr = _cargar(entrada)
    w, h = im.size
    lado = max(w, h)
    info = None
    try:
        info = analizar(entrada)
    except Exception:
        info = {}

    sigma = info.get("sigma", 0.01)
    block = info.get("blockiness", 1.0)

    # --- 1) DEBLOCK + DENOISE en resolución ORIGINAL (pequeña = rápido y correcto:
    #        se limpia la compresión ANTES de agrandar, no se agrandan los bloques).
    fuerza_ruido = _slider(ruido, 1.0, k)
    if _SK and fuerza_ruido > 0.01 and (sigma > 0.008 or block > 1.2):
        # peso adaptativo: más ruido/bloques -> más limpieza, pero con techo suave
        peso = min(0.14, (max(sigma, (block - 1) * 0.03)) * 1.4) * fuerza_ruido
        if peso > 0.002:
            try:
                arr = restoration.denoise_tv_chambolle(
                    arr, weight=float(peso), channel_axis=-1).astype(np.float32)
            except Exception:
                pass
        # un pase bilateral MUY suave respeta bordes tras el TV (sin emborronar)
        try:
            arr = restoration.denoise_bilateral(
                arr, sigma_color=float(0.035 * fuerza_ruido),
                sigma_spatial=1.0, channel_axis=-1).astype(np.float32)
        except Exception:
            pass
    elif not _SK and fuerza_ruido > 0.3:
        im2 = Image.fromarray((np.clip(arr, 0, 1) * 255).astype("uint8"))
        im2 = im2.filter(ImageFilter.MedianFilter(3))
        arr = np.asarray(im2, dtype=np.float32) / 255.0

    # --- 2) COLOR: balance de blancos gray-world (amortiguado) + luz global.
    fuerza_color = _slider(color, 1.0, k)
    if fuerza_color > 0.01:
        medios = arr.reshape(-1, 3).mean(axis=0) + 1e-6
        gris = medios.mean()
        ganancia = 1.0 + (gris / medios - 1.0) * min(1.0, 0.5 * fuerza_color)
        arr = np.clip(arr * ganancia, 0, 1)

    # luz/contraste global suave por percentiles de la luminancia
    fuerza_luz = _slider(luz, 1.0, k)
    fuerza_ct = _slider(contraste, 1.0, k)
    if fuerza_luz > 0.01 or fuerza_ct > 0.01:
        Y = _lum(arr)
        lo, hi = np.percentile(Y, 0.5), np.percentile(Y, 99.5)
        if hi - lo > 1e-3:
            estirado = np.clip((arr - lo) / (hi - lo), 0, 1)
            mezcla = min(1.0, 0.6 * max(fuerza_ct, fuerza_luz))
            arr = (arr * (1 - mezcla) + estirado * mezcla).astype(np.float32)
        # corrección de exposición: acerca la media a ~0.5 con gamma suave
        if fuerza_luz > 0.01:
            m = float(_lum(arr).mean())
            if 0.05 < m < 0.95:
                import math
                objetivo = 0.46
                gamma = math.log(objetivo + 1e-6) / math.log(m + 1e-6)
                gamma = 1.0 + (gamma - 1.0) * min(1.0, 0.5 * fuerza_luz)
                gamma = max(0.6, min(1.6, gamma))
                arr = np.clip(arr, 0, 1) ** (1.0 / gamma)

    # --- 3) UPSCALE Lanczos (solo agrandar; nunca reducir aquí).
    if resolucion is not None and resolucion > 0:
        objetivo = int(resolucion)
    else:
        if lado < 1080:
            objetivo = min(MAX_LADO, int(round(lado * 2.0)))
        elif lado < 1500:
            objetivo = min(MAX_LADO, int(round(lado * 1.5)))
        else:
            objetivo = min(MAX_LADO, lado)
    objetivo = max(objetivo, lado if lado <= MAX_LADO else MAX_LADO)
    im_proc = Image.fromarray((np.clip(arr, 0, 1) * 255.0 + 0.5).astype("uint8"))
    if objetivo != lado:
        escala = objetivo / float(lado)
        nw, nh = int(round(w * escala)), int(round(h * escala))
        im_proc = im_proc.resize((nw, nh), Image.LANCZOS)

    # --- 4) NITIDEZ (unsharp con PIL) + CLARIDAD (CLAHE suave SOLO en luminancia).
    #        OJO: se evita filters.unsharp_mask de skimage 0.25 — con float32 desborda
    #        y ennegrece la imagen. PIL UnsharpMask (uint8) es estable y natural. El
    #        CLAHE se aplica al canal Y (YCbCr) para no distorsionar el color en sombras.
    fuerza_nit = _slider(nitidez, 1.0, k)
    if fuerza_nit > 0.01:
        amt = 0.68 * fuerza_nit + (0.32 if block > 1.3 else 0.0)
        pct = int(max(30, min(220, round(amt * 115))))
        im_proc = im_proc.filter(ImageFilter.UnsharpMask(radius=1.5, percent=pct, threshold=2))
    fuerza_cl = _slider(claridad, 1.0, k)
    if _SK and fuerza_cl > 0.01:
        try:
            y, cb, cr = im_proc.convert("YCbCr").split()
            Y = np.asarray(y, dtype=np.float64) / 255.0
            clip = float(min(0.02, 0.006 * fuerza_cl))
            Yc = exposure.equalize_adapthist(np.clip(Y, 0, 1), clip_limit=clip)
            mezcla = min(0.55, 0.4 * fuerza_cl)
            nuevoY = np.clip(Y * (1 - mezcla) + Yc * mezcla, 0, 1)
            y2 = Image.fromarray((nuevoY * 255.0 + 0.5).astype("uint8"))
            im_proc = Image.merge("YCbCr", (y2, cb, cr)).convert("RGB")
        except Exception:
            pass
    elif not _SK and fuerza_nit <= 0.01:
        im_proc = ImageOps.autocontrast(im_proc, cutoff=0.5)

    # --- 5) SATURACIÓN final leve (color con vida, sin exagerar).
    if fuerza_color > 0.01:
        sat = 1.0 + min(0.18, 0.10 * fuerza_color)
        im_proc = ImageEnhance.Color(im_proc).enhance(sat)

    # --- guardar (no destructivo: 'salida' es un archivo nuevo).
    ext = (formato or os.path.splitext(salida)[1].lstrip(".") or "jpg").lower()
    os.makedirs(os.path.dirname(os.path.abspath(salida)) or ".", exist_ok=True)
    if ext in ("jpg", "jpeg"):
        im_proc.save(salida, "JPEG", quality=92, subsampling=0, optimize=True)
    elif ext == "webp":
        im_proc.save(salida, "WEBP", quality=94, method=6)
    else:
        im_proc.save(salida, "PNG", optimize=True)
    return {"ok": True, "salida": salida, "w": im_proc.size[0], "h": im_proc.size[1],
            "lado_original": lado, "escalado": objetivo != lado, "analisis": info}


# -------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Realce natural de fotos de baja calidad.")
    ap.add_argument("entrada")
    ap.add_argument("salida", nargs="?")
    ap.add_argument("--analizar", action="store_true", help="Solo analiza y devuelve JSON.")
    ap.add_argument("--nivel", default="auto", choices=["suave", "auto", "intensiva"])
    for opt in ("nitidez", "ruido", "claridad", "contraste", "color", "luz", "resolucion"):
        ap.add_argument("--" + opt, type=int, default=-1)
    ap.add_argument("--formato", default=None, choices=[None, "jpg", "png", "webp"])
    a = ap.parse_args()

    if a.analizar:
        print(json.dumps(analizar(a.entrada), ensure_ascii=False))
        return
    if not a.salida:
        ap.error("falta la ruta de salida (o usa --analizar)")
    r = mejorar(a.entrada, a.salida, nivel=a.nivel, nitidez=a.nitidez, ruido=a.ruido,
                claridad=a.claridad, contraste=a.contraste, color=a.color, luz=a.luz,
                resolucion=a.resolucion, formato=a.formato)
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
