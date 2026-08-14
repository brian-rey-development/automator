"""Tests for the configuration model and its persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from automator.config import (
    AppConfig,
    ConfigStore,
    SocietyMapping,
    default_config,
    load_config,
    save_config,
)


def test_cuit_is_normalized_to_digits() -> None:
    society = SocietyMapping(cuit="30-11111111-8", name="EMPRESA EJEMPLO", folder=Path("/x"))
    assert society.cuit == "30111111118"


def test_cuit_with_wrong_length_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SocietyMapping(cuit="123", name="X", folder=Path("/x"))


def test_cuit_with_bad_check_digit_is_rejected() -> None:
    # 11 digits but an incorrect check digit (the valid one ends in 8).
    with pytest.raises(ValidationError):
        SocietyMapping(cuit="30111111110", name="X", folder=Path("/x"))


def test_folder_for_cuit_returns_society_folder() -> None:
    society = SocietyMapping(cuit="30111111118", name="EMPRESA EJEMPLO", folder=Path("/salida/empresa"))
    config = default_config().model_copy(update={"societies": (society,)})
    assert config.folder_for_cuit(society.cuit) == society.folder


def test_folder_for_cuit_falls_back_to_unknown() -> None:
    config = default_config()
    assert config.folder_for_cuit(None) == config.unknown_folder
    assert config.folder_for_cuit("00000000000") == config.unknown_folder


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    original = default_config()
    save_config(original, path)
    loaded = load_config(path)
    assert loaded == original


def test_load_missing_file_returns_default(tmp_path: Path) -> None:
    assert load_config(tmp_path / "no-existe.json") == default_config()


def test_ensure_folders_creates_all_targets(tmp_path: Path) -> None:
    base = tmp_path / "salida"
    config = AppConfig(
        input_folder=tmp_path / "entrada",
        base_output_folder=base,
        unknown_folder=base / "_sin",
        quarantine_folder=base / "_err",
        societies=[SocietyMapping(cuit="30111111118", name="A", folder=base / "a")],
    )
    config.ensure_folders()
    for folder in config.all_folders():
        assert folder.is_dir()


def test_config_snapshot_is_immutable() -> None:
    store = ConfigStore(default_config())
    snapshot = store.get()
    with pytest.raises(ValidationError):  # frozen: the snapshot cannot be mutated.
        snapshot.dry_run = True  # type: ignore[misc]
    assert store.get().dry_run is False  # The store stays intact.


def test_stability_timeout_is_bounded() -> None:
    with pytest.raises(ValidationError):
        AppConfig(
            input_folder=Path("/a"),
            base_output_folder=Path("/b"),
            unknown_folder=Path("/c"),
            quarantine_folder=Path("/d"),
            stability_timeout_s=999.0,
        )


def test_duplicate_cuits_are_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig(
            input_folder=Path("/a"),
            base_output_folder=Path("/b"),
            unknown_folder=Path("/c"),
            quarantine_folder=Path("/d"),
            societies=[
                SocietyMapping(cuit="30111111118", name="Uno", folder=Path("/x")),
                SocietyMapping(cuit="30-11111111-8", name="Dos", folder=Path("/y")),
            ],
        )


def test_corrupt_config_falls_back_to_default_and_is_backed_up(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"esquema": "viejo", "otro": 1}', encoding="utf-8")
    loaded = load_config(path)
    assert loaded == default_config()
    # The backup carries a timestamp so it does not overwrite prior diagnostics.
    assert list(tmp_path.glob("config.json.*.corrupt"))


def test_unreadable_json_falls_back_to_default(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("esto no es json", encoding="utf-8")
    assert load_config(path) == default_config()


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    save_config(default_config(), path)
    assert path.exists()
    assert not (tmp_path / "config.json.tmp").exists()


def test_config_store_set_replaces_config() -> None:
    store = ConfigStore(default_config())
    incoming = default_config().model_copy(update={"dry_run": True})
    store.set(incoming)
    assert store.get().dry_run is True


def test_society_folder_must_be_absolute() -> None:
    with pytest.raises(ValidationError):
        SocietyMapping(cuit="30111111118", name="X", folder=Path(""))
    with pytest.raises(ValidationError):
        SocietyMapping(cuit="30111111118", name="X", folder=Path("relativa/sub"))


def test_society_name_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        SocietyMapping(cuit="30111111118", name="   ", folder=Path("/x"))


def test_output_folder_inside_input_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig(
            input_folder=Path("/data/entrada"),
            base_output_folder=Path("/data/entrada/salida"),  # nested inside the input
            unknown_folder=Path("/data/sin"),
            quarantine_folder=Path("/data/err"),
        )


def test_invalid_template_token_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig(
            input_folder=Path("/a"),
            base_output_folder=Path("/b"),
            unknown_folder=Path("/c"),
            quarantine_folder=Path("/d"),
            destination_template="{proveedor}",  # invalid token (it is {supplier})
        )


def test_review_folder_is_under_output() -> None:
    config = default_config()
    assert config.review_folder.parent == config.base_output_folder
    assert config.review_folder in config.all_folders()
