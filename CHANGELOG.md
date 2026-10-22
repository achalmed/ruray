---
tipo: changelog
estado: activo
---
# CHANGELOG — ruray

## [Unreleased]

### Añadido

- **Las páginas del editor de piezas, en Awana** (2026-10-21, al nacer Awana): `editor.html` y sus scripts,
  `preprensa.py` y `embeber-foto.py` salen a su repositorio, con sus pruebas. Aquí quedan el servidor del estudio, lo
  común de las páginas y los motores (`estudio/editor/README.md`, reescrito).
- **La página del editor de videos, en Kuyuy** (2026-10-21, al nacer Kuyuy): `video.html` y ffmpeg.wasm
  (`estudio/editor/vendor/ffmpeg/`) salen a su repositorio. `montaje.py` y `video/shorts/` se quedan: el servidor del
  estudio los importa al cargarse.
- **Las páginas propias de cada editor, en su repositorio** (2026-10-21, al nacer Tullpu): `Editor.carpeta` (lo de
  `paginas` se busca primero allí; lo común del estudio, aquí) y `ruray.pruebas`, el entorno de prueba común de los
  editores (el servidor del estudio con un perfil temporal y la Mediateca falsa, que venían de las pruebas del editor de
  fotos en Qillqa). Las páginas del editor de fotos (`foto.html`, `foto-lienzo.html`, `media.html` y miniPaint) y sus
  pruebas salen a Tullpu. La demo ya no cambia los textos neutros del estudio: deben ser iguales en el servidor, las
  páginas de cada editor y el kit común.
- **Ruray nace** (2026-10-21, fase 10.3 de Qillqa): la base común de los editores sale de Qillqa (commit `8a0d91a`) con
  su puente a FastAPI (`ruray/comun.py`), el de la Mediateca (`ruray/mediateca.py`), el estudio entero (`estudio/`) y
  sus pruebas; su prueba de fronteras exige que no importe nada de Qillqa. Los textos neutros del estudio vuelven a ser
  iguales a los de las plantillas de Unancha («correo@institucion.gob»), como pide su prueba.
