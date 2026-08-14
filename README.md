# Automator - Clasificador de facturas AFIP

Autor: Brian Rey

Aplicacion de escritorio que vigila una carpeta de descargas, lee cada factura
en PDF, detecta el tipo de comprobante, el numero, el proveedor y la sociedad
compradora (por CUIT), y archiva el PDF renombrado en la carpeta correcta.

Reemplaza al script original de una sola pieza por una aplicacion completa con
interfaz grafica moderna, configuracion persistente, manejo de errores robusto
y una bateria de tests.

## Caracteristicas

- Interfaz moderna (CustomTkinter) pensada para usarse sin experiencia previa:
  etiquetas claras, textos de ayuda y selectores de carpeta en todos lados.
- Deteccion de tipo y letra de comprobante por codigo AFIP, con respaldo por texto.
- Ruteo por CUIT a la carpeta de cada sociedad, configurable desde la interfaz.
- Carpeta "para revisar" automatica cuando la extraccion no es confiable, para
  evitar archivar mal una factura sin que nadie se entere.
- Procesa solo lo que ya estaba en la carpeta al iniciar y reintenta de forma
  periodica los archivos que hayan quedado pendientes.
- Espera a que termine la descarga antes de mover (evita archivos a medio bajar).
- Sin sobrescrituras: si el nombre existe, agrega ` (2)`, ` (3)`, etc.
- Cuarentena automatica de PDFs ilegibles o con errores, sin frenar el monitor.
- Configuracion validada, guardada de forma atomica y con recuperacion si el
  archivo se corrompe (no puede dejar la app sin abrir).
- Modo de prueba para ver que haria sin mover nada, y logs rotativos.

## Requisitos

- Python 3.11 o superior.
- Windows para el ejecutable final (el codigo corre tambien en macOS y Linux).

## Uso en desarrollo

Con `make` (recomendado):

```bash
make install   # crea el entorno virtual e instala todo
make run       # ejecuta la aplicacion
make demo      # genera facturas de ejemplo y abre la app para probarla
make check     # linting + tipos + tests
```

`make demo` crea PDFs de ejemplo en la carpeta de entrada que cubren todos los
casos (archivado por sociedad, sin clasificar, para revisar y cuarentena). Al
abrir la app, apreta "Iniciar" para verlos procesarse en tiempo real.

Sin `make`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m automator
```

En macOS o Linux el equivalente es `python3 -m venv .venv && source .venv/bin/activate`.
No hace falta `uv`; si lo tenes, `uv pip install -e ".[dev]"` tambien funciona.

Para instalar los hooks de calidad antes de cada commit: `pre-commit install`.

## Generar el ejecutable de Windows

```powershell
.\scripts\build_windows.ps1
```

El ejecutable queda en `dist\Automator.exe`. Es un unico archivo, sin consola,
que se puede copiar y ejecutar en cualquier PC con Windows.

## Calidad

```bash
ruff check .      # linting (rapido)
ruff format .     # formateo
mypy              # tipos estrictos
pytest            # tests con cobertura del nucleo
```

## Arquitectura

El proyecto separa el nucleo puro (sin efectos secundarios y 100% testeable) de
los servicios con entrada/salida y de la interfaz.

```
src/automator/
  domain/      Modelos, parser, nombres y clasificacion (logica pura)
  services/    Lectura de PDF, IO de archivos, watcher y motor de procesamiento
  ui/          Interfaz de escritorio (CustomTkinter)
  config.py    Modelo de configuracion validado y persistencia
tests/         Bateria de tests del nucleo y los servicios
```

El motor corre en un hilo de fondo y se comunica con la interfaz mediante una
cola de eventos, respetando que Tkinter no es seguro entre hilos.
