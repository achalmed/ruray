#!/usr/bin/env python3
"""editor/lote_gimp.py — prepara fotos para redes en lote con GIMP (sin interfaz).

Complementa a `mejorar_foto.py` (que se ocupa de la CALIDAD: ruido, nitidez, contraste) con lo
que GIMP hace mejor que Pillow:

  1. convierte el perfil de color a sRGB (lo que esperan las redes y los navegadores);
  2. recorta al centro y escala a los formatos de `tokens/layout.json`
     (cuadrado 1080×1080, retrato 1080×1350, vertical 1080×1920, horizontal 1920×1080);
  3. exporta en JPEG **sin** EXIF, XMP, IPTC ni miniatura: se van la ubicación GPS, la cámara y
     la fecha, que no deben salir en una foto de campo.

Uso:
  lote_gimp.py <fotos o carpetas> --salida DIR [--formatos cuadrado,retrato] [--estirar-niveles]
               [--calidad 88] [--aplicar]

Simula por defecto (dice qué escribiría); con --aplicar escribe. Nunca toca los originales y se
niega a escribir en la carpeta de entrada. Usa `gimp-console` nativo (APT) si existe y, si no, el
de Flatpak (org.gimp.GIMP).
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # raíz del repo: lib/nucleo
from lib import nucleo  # noqa: E402  raíz y logger de core/ (RQ-COD-06)

log = nucleo.registro("identidad-visual.lote_gimp")

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = str(nucleo.RAIZ)
EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic")

# Nombre corto → clave en tokens/layout.json (única fuente de las dimensiones).
FORMATOS = {"cuadrado": "social_1080", "retrato": "retrato_1080x1350",
            "vertical": "story_1080x1920", "horizontal": "presentacion_16x9"}


def gimp_console():
    """GIMP sin interfaz: el nativo (APT) si existe; si no, el Flatpak. La decisión vive en un solo
    sitio del estudio, lib/herramientas.py (herramienta)."""
    from lib.herramientas import herramienta   # la raíz del estudio ya está en sys.path (lib/nucleo)
    cmd, _via = herramienta("gimp-console")
    if not cmd:
        nucleo.abortar(log, "no hay GIMP (ni APT ni Flatpak)")
    return cmd


def dimensiones(nombres):
    with open(os.path.join(RAIZ, "tokens", "layout.json"), encoding="utf-8") as f:
        formatos = json.load(f)["formatos"]
    out = {}
    for n in nombres:
        if n not in FORMATOS:
            nucleo.abortar(log, "formato desconocido: %s (hay: %s)" % (n, ", ".join(FORMATOS)))
        out[n] = formatos[FORMATOS[n]]["px"]
    return out


def fotos(entradas):
    for e in entradas:
        if os.path.isdir(e):
            for n in sorted(os.listdir(e)):
                if n.lower().endswith(EXT):
                    yield os.path.abspath(os.path.join(e, n))
        elif e.lower().endswith(EXT) and os.path.isfile(e):
            yield os.path.abspath(e)


# Programa que corre DENTRO de GIMP (python-fu-eval). Recibe el trabajo como JSON.
PROGRAMA = r'''
import json
from gi.repository import Gimp, Gio
trabajo = json.loads(%r)
pdb = Gimp.get_pdb()
exportar = pdb.lookup_procedure("file-jpeg-export")
srgb = Gimp.ColorProfile.new_rgb_srgb()
Gimp.context_set_interpolation(Gimp.InterpolationType.CUBIC)
for t in trabajo["fotos"]:
    base = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(t["entrada"]))
    base.flatten()
    base.convert_color_profile(srgb, Gimp.ColorRenderingIntent.PERCEPTUAL, True)
    if trabajo["estirar"]:
        base.get_layers()[0].levels_stretch()
    for nombre, (w, h) in trabajo["formatos"].items():
        img = base.duplicate()
        W, H = img.get_width(), img.get_height()
        if W * h > H * w:                       # sobra ancho: recorte lateral al centro
            nw = int(round(H * w / h)); img.crop(nw, H, (W - nw) // 2, 0)
        else:                                   # sobra alto: recorte al centro
            nh = int(round(W * h / w)); img.crop(W, nh, 0, (H - nh) // 2)
        img.scale(w, h)
        cfg = exportar.create_config()
        cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
        cfg.set_property("image", img)
        cfg.set_property("file", Gio.File.new_for_path(t["salidas"][nombre]))
        cfg.set_property("quality", trabajo["calidad"])
        for p in ("include-exif", "include-iptc", "include-xmp", "include-thumbnail", "include-comment"):
            cfg.set_property(p, False)
        cfg.set_property("include-color-profile", True)
        exportar.run(cfg)
        img.delete()
        print("LOTE_GIMP_OK", t["salidas"][nombre])
    base.delete()
'''


def main():
    ap = argparse.ArgumentParser(description="Fotos para redes en lote con GIMP: sRGB, formatos de la marca, sin metadatos.")
    ap.add_argument("entradas", nargs="+")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--formatos", default="cuadrado,retrato")
    ap.add_argument("--estirar-niveles", action="store_true", help="estira niveles (fotos apagadas)")
    ap.add_argument("--calidad", type=int, default=88)
    ap.add_argument("--aplicar", action="store_true", help="escribe de verdad (por defecto simula)")
    a = ap.parse_args()

    salida = os.path.abspath(os.path.expanduser(a.salida))
    formatos = dimensiones([f.strip() for f in a.formatos.split(",") if f.strip()])
    trabajo = {"fotos": [], "formatos": formatos, "calidad": a.calidad / 100.0, "estirar": a.estirar_niveles}
    for f in fotos(a.entradas):
        if os.path.dirname(f) == salida:
            nucleo.abortar(log, "la salida no puede ser la carpeta de las fotos originales")
        stem = os.path.splitext(os.path.basename(f))[0]
        trabajo["fotos"].append({"entrada": f, "salidas": {
            n: os.path.join(salida, "%s-%s.jpg" % (stem, n)) for n in formatos}})
    if not trabajo["fotos"]:
        nucleo.abortar(log, "no hay fotos (%s)" % ", ".join(EXT))
    for t in trabajo["fotos"]:
        print("· %s → %s%s" % (os.path.basename(t["entrada"]), ", ".join(os.path.basename(s) for s in t["salidas"].values()),
                               "" if a.aplicar else "  (simulación)"))
    if not a.aplicar:
        print("Simulación: nada se escribió. Use --aplicar. GIMP: %s" % " ".join(gimp_console()))
        return
    os.makedirs(salida, exist_ok=True)
    cmd = gimp_console() + ["-i", "--quit", "--batch-interpreter=python-fu-eval", "-b", PROGRAMA % json.dumps(trabajo)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    hechos = [l.split(" ", 1)[1] for l in r.stdout.splitlines() if l.startswith("LOTE_GIMP_OK ")]
    esperados = sum(len(t["salidas"]) for t in trabajo["fotos"])
    print("GIMP escribió %d de %d archivos" % (len(hechos), esperados))
    if len(hechos) != esperados:
        nucleo.abortar(log, (r.stderr or r.stdout)[-1200:])


if __name__ == "__main__":
    main()
