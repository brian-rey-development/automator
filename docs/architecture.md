# Arquitectura

Automator separa la logica pura de los efectos secundarios y de la interfaz, en
tres capas con dependencias hacia adentro: `ui -> services -> domain`. El nucleo
no sabe que existe una interfaz grafica ni un disco.

```
src/automator/
  domain/      Logica pura y 100% testeable (sin IO)
  services/    IO y orquestacion (PDF, archivos, watcher, motor, historial)
  ui/          Interfaz de escritorio (CustomTkinter)
  config.py    Modelo de configuracion validado e inmutable + persistencia
```

## Capa de dominio (`domain/`)

Funciones puras y deterministas, sin efectos secundarios:

- `models.py` - modelos inmutables: `Voucher`, `ParsedInvoice`, `ProcessOutcome`,
  `ProcessResult`. `ParsedInvoice` expone propiedades derivadas (`has_number`,
  `has_supplier`, `identity`).
- `parser.py` - extrae tipo/letra (por codigo AFIP con respaldo por texto),
  numero, proveedor, CUIT comprador y fecha. **Nunca lanza**: ante texto
  inesperado devuelve defaults deterministas.
- `classifier.py` - resuelve la carpeta destino aplicando la plantilla.
- `filenames.py` - saneado de nombres para Windows y armado del nombre final.

## Capa de servicios (`services/`)

- `pdf_reader.py` - extrae texto con cierre deterministico del archivo y
  resiliencia por pagina.
- `file_ops.py` - movimientos atomicos, sin sobrescribir, con soporte de rutas
  largas y UNC en Windows.
- `watcher.py` - vigila la carpeta de entrada (watchdog).
- `processor.py` - orquesta el procesamiento de un PDF y decide su destino.
- `engine.py` - motor en segundo plano: cola, worker, reescaneo periodico.
- `ledger.py` - historial de auditoria en SQLite (base de historial, duplicados
  y deshacer).

## Capa de interfaz (`ui/`)

CustomTkinter. No contiene reglas de negocio: solo muestra estado y dispara
acciones del motor. `main_window.py` coordina; `onboarding.py` y
`society_dialog.py` son dialogos; `theme.py` es el design system; `system_utils.py`
abre carpetas y muestra notificaciones.

## Modelo de concurrencia

```
watcher (hilo)  ─┐
                 ├─> queue.Queue ─> worker (hilo) ─> EngineEvent ─┐
rescan (hilo)   ─┘                                                │
                                                                  v
                              queue.Queue de eventos <── UI (hilo Tkinter)
                                    _poll_events (after 150ms)
```

- El motor corre en un hilo de fondo; la UI nunca se bloquea.
- La comunicacion motor -> UI es via `EngineEvent` en una cola que se drena solo
  desde el hilo de Tkinter. **Tkinter no es thread-safe.**
- La cola de trabajo y la señal de parada se recrean por cada arranque
  ("generacion"): un worker viejo que tarde en terminar nunca comparte cola con
  uno nuevo, y un nuevo arranque se rechaza mientras el anterior siga vivo.
- Un `set` de archivos en vuelo evita encolar dos veces el mismo PDF.

## Flujo de un archivo

```
PDF nuevo -> wait_until_stable -> extract_text
          -> parse_invoice
          -> ambiguo?      -> _PARA_REVISAR
          -> no confiable? -> _PARA_REVISAR
          -> duplicado?    -> _DUPLICADOS
          -> sin CUIT?     -> _SIN_CLASIFICAR
          -> ok            -> carpeta de la sociedad (segun plantilla)
          (ilegible/error) -> _ERRORES (cuarentena)
```

Cada resultado se registra en el ledger, pase lo que pase (salvo archivos que ya
no existen).

## Persistencia

- Configuracion: `config.json` (guardado atomico, recuperacion ante corrupcion).
- Historial: `history.db` (SQLite).
- Logs: `automator.log` rotativo.

Las rutas se resuelven con `platformdirs` (`config_path`, `ledger_path`,
`log_dir`), por lo que respetan las convenciones de cada sistema operativo.
