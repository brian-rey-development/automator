# Funcionalidades

Todo es configurable desde la interfaz. La app no trae ninguna empresa ni CUIT
precargado: en el primer arranque un asistente ayuda a definir lo minimo.

## Clasificacion de facturas

- **Deteccion de comprobante** por codigo AFIP (01 = FC A, 06 = FC B, 08 = NC B,
  etc.), con respaldo por texto cuando el codigo no aparece.
- **Numero y punto de venta**, tolerando el layout separado y el combinado.
- **Proveedor** desde la etiqueta "Razon Social". Si no se detecta con confianza,
  la factura va a revision (no se archiva bajo un nombre inventado).
- **Sociedad compradora** por CUIT, contra las sociedades configuradas.
- **Fecha de emision**, usada por la plantilla de carpetas.

## Ruteo seguro

Cada factura termina en un lugar segun que tan confiable fue la lectura:

| Situacion | Destino | Estado |
|---|---|---|
| Se detecto la sociedad compradora | Carpeta de la sociedad | Archivado |
| No se detecto el CUIT comprador | `_SIN_CLASIFICAR` | Sin clasificar |
| Ya se habia archivado (duplicado) | `_DUPLICADOS` | Duplicado |
| Datos incompletos o proveedor dudoso | `_PARA_REVISAR` | Revisar |
| Aparecen varias sociedades propias | `_PARA_REVISAR` | Revisar |
| PDF ilegible o error | `_ERRORES` | Cuarentena |

El principio es **nunca archivar mal en silencio**: ante la duda, a revision.

## Estructura de carpetas configurable

Dentro de la carpeta de cada sociedad se aplica una plantilla con tokens:

- `{supplier}` - razon social del proveedor
- `{society}` - carpeta de la sociedad
- `{year}` `{month}` `{day}` - de la fecha de emision (o `sin_fecha`)

Ejemplos: `{supplier}` (por defecto) archiva por proveedor;
`{year}/{month}/{supplier}` archiva por ano y mes.

## Historial de auditoria

Todo lo procesado se guarda en SQLite y sobrevive al cierre de la app. La vista
"Historial" lo muestra con su resultado y destino. Sobre esta base:

- **Deshacer**: devuelve el ultimo movimiento a la carpeta de entrada (con el
  monitor detenido, para no reprocesarlo al instante).
- **Reintentar pendientes**: reprocesa lo que quedo en revision y cuarentena,
  util despues de agregar una sociedad o corregir la configuracion.

## Deteccion de duplicados

Una factura se identifica por `proveedor | numero | tipo`. Si ya fue archivada
antes (segun el historial), la nueva copia va a `_DUPLICADOS` en vez de
duplicarse. Util cuando AFIP permite re-descargar el mismo comprobante.

## Robustez

- Espera a que termine la descarga antes de mover (evita archivos a medio bajar).
- Movimientos atomicos y sin sobrescribir (agrega ` (2)`, ` (3)`, ...).
- Cuarentena de ilegibles sin frenar el monitor; reescaneo periodico de la
  carpeta por si el watcher pierde un evento.
- Configuracion validada e inmutable, guardada de forma atomica, con respaldo si
  el archivo se corrompe (nunca deja la app sin abrir).

## Avisos y utilidades

- **Aviso persistente de pendientes** leido de las carpetas (no depende de un
  unico evento de la interfaz).
- **Notificacion del sistema** opcional cuando aparecen nuevos pendientes.
- **Modo de prueba** (dry-run): muestra que haria sin mover nada.
- Botones para abrir las carpetas de entrada, salida, revision y logs.

## Primer arranque

Al abrir la app por primera vez, un asistente pide lo minimo (carpeta de entrada,
carpeta de salida y, opcionalmente, una primera empresa). Todo se puede cambiar
despues desde Configuracion.
