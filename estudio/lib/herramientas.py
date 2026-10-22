"""lib/herramientas.py — con qué orden se llama a Inkscape o a GIMP sin interfaz: la instalación nativa (APT) si está en el PATH; si
no, la del Flatpak.

Copia mínima de `herramienta()` de los adaptadores de Unancha (su `adaptadores/lib/herramientas.py`), para que el estudio no
importe código de otro repo (fase 10.2b, 2026-10-21: al retirar de Unancha la copia vieja del estudio, `shorts.py portadas` y
`editor/lote_gimp.py` quedaron sin ese import). Allá siguen los envoltorios de ~/.local/bin, las carpetas de usuario y la
instalación de las plantillas; aquí solo se elige la orden. Un envoltorio de Unancha en el PATH cuenta como nativo: corre el
mismo Flatpak. Solo la librería estándar.
"""
import shutil
import subprocess

# Herramienta → (aplicación Flatpak, orden dentro del Flatpak, nombres nativos posibles), como en Unancha.
HERRAMIENTAS = {
    "inkscape": ("org.inkscape.Inkscape", None, ("inkscape",)),
    "gimp-console": ("org.gimp.GIMP", "gimp-console", ("gimp-console-3.2", "gimp-console-3", "gimp-console")),
}


def nativo(*nombres):
    """El primer ejecutable del PATH con alguno de esos nombres, o None."""
    for n in nombres:
        ruta = shutil.which(n)
        if ruta:
            return ruta
    return None


def flatpak_tiene(app):
    return bool(shutil.which("flatpak")) and subprocess.run(
        ["flatpak", "info", app], capture_output=True).returncode == 0


def herramienta(nombre):
    """(orden, vía): la nativa si existe (APT manda), si no la del Flatpak; (None, None) si no hay ninguna."""
    app, orden, nombres = HERRAMIENTAS[nombre]
    ruta = nativo(*nombres)
    if ruta:
        return [ruta], "APT"
    if flatpak_tiene(app):
        return ["flatpak", "run"] + (["--command=" + orden] if orden else []) + [app], "Flatpak"
    return None, None
