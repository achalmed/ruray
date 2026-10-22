---
tipo: readme
estado: activo
---
# editor/ — el servidor del estudio y lo común de las páginas de los editores

Desde el 2026-10-21 las páginas de cada editor viven en su repositorio, en `paginas/`, y la base común (`ruray.comun`,
`Editor.carpeta`) las sirve desde allí: `editor.html` en Awana, `foto.html` y `media.html` en Tullpu, `video.html` en
Kuyuy. Aquí queda lo que comparten: el servidor del estudio, el aspecto común y los motores que el servidor llama.

## Uso

```bash
export IDENTIDAD_PERFIL=/ruta/al/perfil/marca/perfil.json   # sin perfil: rutas relativas de servidor/config.py
python3 estudio/editor/servidor/servidor.py                 # suelto, sin anfitrión (para probar una ruta)
curl -s http://127.0.0.1:8099/api/health                     # {"ok": true, …} si está arriba
```

Dentro de un anfitrión no corre aparte: `ruray.comun` carga sus funciones y cada editor monta solo sus rutas.

## Estructura

| archivo | qué es |
|---|---|
| `servidor/` | el servidor del estudio: `config.py` (rutas y opciones, sobreescritas por el perfil), `servidor.py` (API) y `montaje.py` (la orden de ffmpeg del editor de video); ver [`servidor/README.md`](servidor/README.md) |
| `estudio-tema.css` | tema único del estudio: tokens `--est-*` y componentes `.est-*` (su bloque de color lo genera el `generar.py` de los adaptadores de Unancha) |
| `estudio-movil.js` | teléfono (≤ 760 px): los paneles de los editores pasan a cajones, la cabecera se desliza y los controles crecen |
| `estudio-iconos.js` | juego único de íconos de la interfaz (SVG en línea de Lucide, ISC): `<i class="ico" data-ico="…">` o `icono("…")` |
| `mejorar_foto.py` | motor de mejora de fotos que el servidor llama como subproceso (`POST api/mejorar-foto`, de Tullpu y Awana) |
| `lote_gimp.py` | fotos para redes en lote con GIMP (`herramientas-de-escritorio.md`, en los docs de Unancha) |

Lo que el servidor escribe y no se versiona (`.gitignore`): `_trabajo/`, `estado-editor/`, `proyectos-media/` y
`proyectos-foto/` cuando no hay perfil, y el pid y el registro del servidor en `servidor/`.

## Límite honesto

- El servidor escucha en `127.0.0.1`; no está pensado para exponerse a internet.
- Fuera de Chrome o Chromium la exportación de video del navegador puede fallar.
