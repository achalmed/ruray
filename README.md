# Ruray — la base de un estudio de piezas, fotos y videos

Ruray («hacer, obrar» en quechua: el taller) es la base sobre la que corren tres editores web: de piezas gráficas, de
fotos y de videos. Trae el estudio (su servidor, sus motores y sus páginas) y lo monta en FastAPI para que cada editor
sirva solo sus rutas, con su propia sesión. Es parte de [Tiqsi](https://github.com/achalmed/tiqsi): los editores son
módulos que funcionan solos o dentro de una plataforma que los monte.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -e '.[pruebas]'   # requiere tiqsi
.venv/bin/python -m pytest -q
```

Esta es una **versión de demostración**. Licencia: AGPL-3.0 (`LICENSE`); las bibliotecas de `estudio/editor/vendor/`,
con la suya.
