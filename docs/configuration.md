# Configuracion

Toda la configuracion se edita desde la interfaz (pestaña Configuracion) y se
guarda en `config.json`. No hace falta tocar el archivo a mano.

## Ubicacion de los archivos

Las rutas siguen las convenciones de cada sistema operativo (via `platformdirs`):

- **Configuracion**: `config.json` en el directorio de config del usuario.
- **Historial**: `history.db` en el directorio de datos del usuario.
- **Logs**: `automator.log` en el directorio de logs del usuario.

Desde la app: Configuracion -> "Abrir carpeta de logs".

## Campos

### Carpetas principales

- **Carpeta de entrada**: donde caen los PDF descargados (se vigila esta carpeta).
- **Carpeta de salida**: raiz donde se guardan las facturas ordenadas.

### Empresas (sociedades)

Lista de sociedades compradoras. Cada una tiene:

- **CUIT**: 11 digitos (se aceptan guiones y puntos, se normaliza solo).
- **Razon social**: nombre visible, no puede estar vacio.
- **Carpeta**: ruta absoluta donde se archivan sus facturas.

Se agregan, editan y eliminan desde la interfaz. La app arranca sin ninguna
empresa: se definen las propias.

### Opciones

- **Modo de prueba**: no mueve nada, solo muestra que haria.
- **Esperar a que termine la descarga**: evita mover archivos a medio bajar.
- **Espera maxima (segundos)**: 0 a 120.
- **Notificaciones**: aviso del sistema cuando aumentan los pendientes.
- **Estructura de carpetas**: plantilla dentro de la carpeta de cada sociedad.

### Carpetas automaticas (avanzado)

- **Sin clasificar**: facturas de un CUIT no configurado.
- **Cuarentena**: PDF ilegibles o con errores.

Ademas, dentro de la carpeta de salida se crean solas: `_PARA_REVISAR` (revision
manual) y `_DUPLICADOS`.

## Plantilla de carpetas

Define subcarpetas dentro de la carpeta de cada sociedad. Tokens validos:

| Token | Valor |
|---|---|
| `{supplier}` | Razon social del proveedor |
| `{society}` | Nombre de la carpeta de la sociedad |
| `{year}` | Ano de la fecha de emision (o `sin_fecha`) |
| `{month}` | Mes (o `sin_fecha`) |
| `{day}` | Dia (o `sin_fecha`) |

Ejemplos:

- `{supplier}` (por defecto) -> `.../Sociedad/PROVEEDOR/factura.pdf`
- `{year}/{month}/{supplier}` -> `.../Sociedad/2026/08/PROVEEDOR/factura.pdf`

Un token invalido se rechaza al guardar.

## Reglas de validacion

- Las carpetas de salida no pueden estar dentro de la carpeta de entrada (evita
  un bucle de reprocesamiento).
- No puede haber CUIT repetidos entre sociedades.
- Las rutas de las sociedades deben ser absolutas.

Si algo no valida, la interfaz lo avisa y no guarda hasta corregirlo.
