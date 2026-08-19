"""Load, collect and persist configuration, including buying companies."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox

from pydantic import ValidationError

from automator.config import AppConfig, ConfigStore, SocietyMapping, log_dir
from automator.services.excel_import import ExcelReadError, MissingColumnError, parse_societies, read_rows
from automator.ui import system_utils
from automator.ui.dialogs.import_report_dialog import ImportReportDialog
from automator.ui.dialogs.society_dialog import SocietyDialog
from automator.ui.presentation import format_validation_error
from automator.ui.system_utils import open_folder
from automator.ui.views.settings import SettingsView

logger = logging.getLogger(__name__)


class SettingsForm:
    def __init__(self, store: ConfigStore, view: SettingsView, widget: tk.Misc) -> None:
        self._store = store
        self._view = view
        self._widget = widget
        self.societies: list[SocietyMapping] = []
        self._is_running: Callable[[], bool] = lambda: False
        self._start: Callable[[], None] = lambda: None
        self._stop: Callable[[], None] = lambda: None

    def bind_monitor(self, is_running: Callable[[], bool], start: Callable[[], None], stop: Callable[[], None]) -> None:
        self._is_running = is_running
        self._start = start
        self._stop = stop

    def load(self) -> None:
        config = self._store.get()
        view = self._view
        view.input_var.set(str(config.input_folder))
        view.output_var.set(str(config.base_output_folder))
        view.unknown_var.set(str(config.unknown_folder))
        view.quarantine_var.set(str(config.quarantine_folder))
        view.orders_var.set(str(config.orders_folder))
        view.dry_run_var.set(config.dry_run)
        view.stability_var.set(config.wait_for_stability)
        view.notify_var.set(config.notify)
        view.copy_var.set(config.copy_files)
        view.timeout_var.set(str(config.stability_timeout_s))
        view.template_var.set(config.destination_template)
        self.societies = list(config.societies)
        self.refresh_societies()

    def refresh_societies(self) -> None:
        self._view.render_societies(self.societies)

    def collect_config(self) -> AppConfig | None:
        paths = (
            self._view.input_var,
            self._view.output_var,
            self._view.unknown_var,
            self._view.quarantine_var,
            self._view.orders_var,
        )
        if any(not var.get().strip() for var in paths):
            messagebox.showerror("Configuracion incompleta", "Todas las carpetas son obligatorias.")
            return None
        timeout = self._parse_timeout()
        if timeout is None:
            return None
        try:
            return self._build_config(timeout)
        except ValidationError as exc:
            messagebox.showerror("Configuracion invalida", format_validation_error(exc))
            return None

    def persist(self, config: AppConfig) -> bool:
        try:
            self._store.update(config)
        except OSError as exc:
            logger.exception("No se pudo guardar la configuracion")
            messagebox.showerror("Error al guardar", f"No se pudo guardar la configuracion: {exc}")
            return False
        return True

    def collect_and_save(self) -> bool:
        config = self.collect_config()
        return config is not None and self.persist(config)

    def save_config(self) -> None:
        config = self.collect_config()
        if config is None:
            return
        running = self._is_running()
        if running:
            self._stop()
        if self.persist(config):
            messagebox.showinfo("Configuracion", "Configuracion guardada correctamente.")
        if running:
            self._start()

    def add_society(self) -> None:
        dialog = SocietyDialog(self._widget)
        self._widget.wait_window(dialog)
        if dialog.result is not None:
            self.societies.append(dialog.result)
            self.refresh_societies()

    def edit_society(self, index: int) -> None:
        dialog = SocietyDialog(self._widget, existing=self.societies[index])
        self._widget.wait_window(dialog)
        if dialog.result is not None:
            self.societies[index] = dialog.result
            self.refresh_societies()

    def remove_society(self, index: int) -> None:
        del self.societies[index]
        self.refresh_societies()

    def import_societies(self) -> None:
        path = _ask_excel()
        if path is None:
            return
        system_utils.run_async(lambda: self._import_societies_from(path))

    def pick_folder(self, var: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(parent=self._widget, title="Selecciona una carpeta")
        if chosen:
            var.set(chosen)

    def open_input(self) -> None:
        open_folder(Path(self._view.input_var.get().strip() or "."))

    def open_output(self) -> None:
        open_folder(Path(self._view.output_var.get().strip() or "."))

    def open_folder_var(self, var: tk.StringVar) -> None:
        open_folder(Path(var.get().strip() or "."))

    def open_logs(self) -> None:
        open_folder(log_dir())

    def _parse_timeout(self) -> float | None:
        try:
            return float(self._view.timeout_var.get().strip().replace(",", "."))
        except ValueError:
            messagebox.showerror("Valor invalido", "El tiempo de espera debe ser un numero.")
            return None

    def _build_config(self, timeout: float) -> AppConfig:
        view = self._view
        return AppConfig(
            input_folder=Path(view.input_var.get().strip()),
            base_output_folder=Path(view.output_var.get().strip()),
            unknown_folder=Path(view.unknown_var.get().strip()),
            quarantine_folder=Path(view.quarantine_var.get().strip()),
            orders_folder=Path(view.orders_var.get().strip()),
            societies=tuple(self.societies),
            dry_run=view.dry_run_var.get(),
            wait_for_stability=view.stability_var.get(),
            stability_timeout_s=timeout,
            destination_template=view.template_var.get().strip() or "{supplier}",
            notify=view.notify_var.get(),
            copy_files=view.copy_var.get(),
        )

    def _import_societies_from(self, path: Path) -> None:
        try:
            report = parse_societies(read_rows(path))
        except ExcelReadError as exc:
            logger.exception("No se pudo leer el Excel %s", path)
            self._ui_error("Error al leer", f"No se pudo leer el Excel: {exc}")
            return
        except MissingColumnError as exc:
            self._ui_error("Excel invalido", str(exc))
            return
        self._widget.after(0, lambda: self._apply_societies(report.created, report.invalid))

    def _apply_societies(self, created: list[SocietyMapping], invalid: list[tuple[int, str]]) -> None:
        merged = {society.cuit: society for society in self.societies}
        merged.update({society.cuit: society for society in created})
        self.societies = list(merged.values())
        self.refresh_societies()
        summary = f"{len(created)} empresas importadas, {len(invalid)} con errores. Recorda guardar."
        ImportReportDialog(self._widget, "Importar empresas", summary, invalid)

    def _ui_error(self, title: str, message: str) -> None:
        self._widget.after(0, lambda: messagebox.showerror(title, message))


def _ask_excel() -> Path | None:
    path = filedialog.askopenfilename(title="Elegi el Excel", filetypes=[("Excel", "*.xlsx")])
    return Path(path) if path else None
