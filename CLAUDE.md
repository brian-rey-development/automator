# CLAUDE.md

Guia para trabajar en este repositorio. Extiende las instrucciones globales del
usuario; ante conflicto, este archivo manda para todo lo especifico del proyecto.

## Que es

Automator (autor: Brian Rey) es una aplicacion de escritorio que vigila una
carpeta de descargas, lee cada factura AFIP en PDF, detecta tipo de comprobante,
numero, proveedor y sociedad compradora (por CUIT), y archiva el PDF renombrado
en la carpeta correcta. Se empaqueta como un `.exe` de Windows.

## Principio rector

**Ninguna factura se archiva mal ni se pierde en silencio.** Ante cualquier
incertidumbre (proveedor no detectado, comprador ambiguo, PDF ilegible), el
archivo va a revision o cuarentena, nunca a un destino adivinado con un "ok".
Todo cambio debe preservar esta invariante.

## Comandos

```bash
make install    # crea .venv e instala app + dev
make run        # ejecuta la app (equivale a python -m automator)
make demo       # genera facturas de ejemplo y abre la app
make check      # lint + tipos + tests (correr antes de commitear)
make build      # genera el icono y el .exe con PyInstaller
```

Herramientas sueltas: `ruff check .`, `ruff format .`, `mypy`, `pytest`.

## Arquitectura

Tres capas, dependencias hacia adentro (ui -> services -> domain):

- `src/automator/domain/` - logica pura, sin efectos secundarios, 100% testeable
  (modelos, parser, clasificacion, nombres). Nunca hace IO.
- `src/automator/services/` - IO y orquestacion: lectura de PDF, operaciones de
  archivo, watcher, motor de procesamiento y ledger (historial en SQLite).
- `src/automator/ui/` - interfaz CustomTkinter. No contiene reglas de negocio.
- `src/automator/config.py` - modelo de configuracion validado e inmutable y su
  persistencia atomica.

### Modelo de concurrencia

El motor (`services/engine.py`) corre en un hilo de fondo con una cola. La UI se
comunica con el via `EngineEvent` en una `queue.Queue` que se drena solo desde el
hilo de Tkinter (`_poll_events`). **Tkinter no es thread-safe: nunca tocar
widgets desde un hilo que no sea el principal.** La cola y la señal de parada se
recrean por cada arranque ("generacion") para que un worker viejo nunca comparta
cola con uno nuevo.

### Datos en disco

- Config: `config.json` en el directorio de config del usuario (platformdirs).
- Historial: `history.db` (SQLite) en el directorio de datos del usuario.
- Logs: `automator.log` rotativo en el directorio de logs del usuario.

Rutas resueltas en `config.py` (`config_path`, `ledger_path`, `log_dir`).

## Convenciones de codigo

- **Identificadores en ingles, comentarios en español.** Comentar solo el porque
  no obvio (una invariante, un workaround), nunca lo que el codigo ya dice.
- TypeScript-equivalente estricto: `mypy --strict`, sin `Any` injustificado.
- Funciones <= 20 lineas, retornos tempranos, inmutabilidad por defecto.
- Sin em dashes en ningun texto (prosa, docs, commits). Usar guiones normales.
- Validar en los bordes (input de usuario, APIs externas); confiar en el interior.
- `AppConfig` y `SocietyMapping` son `frozen`: para cambiar la config se construye
  un objeto nuevo, no se muta. `ConfigStore.get()` devuelve el snapshot compartido.

## Testing

- El nucleo (`domain/` y `services/`) se testea con pytest; apuntar a cubrir cada
  rama de decision del procesamiento (movido, sin clasificar, duplicado, revision,
  cuarentena).
- La UI no tiene tests automatizados (limitacion conocida de apps Tkinter); se
  valida con smokes manuales. Al tocar la UI, correr un smoke que construya
  `MainWindow` sin excepciones.
- `tests/conftest.py` tiene textos de factura de ejemplo y una fabrica `make_config`.

## Gotchas

- Movimientos de archivo atomicos (`os.replace`) y sin sobrescribir (sufijo ` (n)`).
- Windows: prefijo de rutas largas y forma `\\?\UNC\` para rutas de red (`file_ops`).
- El parser nunca lanza: ante texto inesperado devuelve defaults deterministas.
- La deteccion de duplicados usa la identidad `proveedor|numero|tipo` contra el
  ledger; solo cuentan como "ya archivada" los resultados MOVED/UNCLASSIFIED.

## Estructura

```
src/automator/      codigo fuente (domain / services / ui / config)
tests/              bateria de tests del nucleo y servicios
scripts/            generadores (icono, facturas de ejemplo) y build de Windows
installer/          script de Inno Setup para el instalador
assets/             icono de marca (.ico / .png)
docs/               arquitectura, features y configuracion
```
