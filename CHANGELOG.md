# Changelog

Todos los cambios relevantes de este proyecto. Formato basado en
[Keep a Changelog](https://keepachangelog.com/); versionado semantico.

## [1.0.0] - 2026-08-14

### Agregado

- Aplicacion de escritorio (CustomTkinter) que clasifica y archiva facturas AFIP
  por sociedad (CUIT), reemplazando el script original de una sola pieza.
- Deteccion de tipo/letra de comprobante por codigo AFIP, numero, proveedor,
  CUIT comprador y fecha de emision.
- Ruteo seguro: sin clasificar, para revisar, cuarentena y duplicados, con el
  principio de nunca archivar mal en silencio.
- Historial de auditoria persistente en SQLite, con deshacer el ultimo
  movimiento y reintentar lo pendiente.
- Deteccion de duplicados por identidad (proveedor, numero, tipo).
- Estructura de carpetas configurable con plantilla (proveedor, ano, mes, dia).
- Asistente de primera vez y notificaciones del sistema opcionales.
- Aviso persistente de pendientes leido de las carpetas.
- Configuracion validada e inmutable, con guardado atomico y recuperacion ante
  corrupcion.
- Icono de marca, empaquetado con PyInstaller e instalador de Windows (Inno
  Setup).
- Tooling: ruff, mypy estricto, pytest, pre-commit y CI en GitHub Actions.

### Notas

- La aplicacion no trae ninguna empresa ni CUIT precargado: todo se configura
  desde la interfaz.
