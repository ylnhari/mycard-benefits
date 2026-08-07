from pathlib import Path

import pytest

from mycard_benefits import config


def test_settings_fall_back_to_packaged_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_root = tmp_path / "installed"
    package_root = tmp_path / "site-packages" / "mycard_benefits"
    packaged_catalog = package_root / "catalog_data"
    packaged_catalog.mkdir(parents=True)
    monkeypatch.setattr(config, "REPO_ROOT", installed_root)
    monkeypatch.setattr(config, "PACKAGE_ROOT", package_root)
    monkeypatch.setattr(config, "resolve_port", lambda *args, **kwargs: 8777)

    settings = config.Settings.from_environment(
        explicit_data_dir=tmp_path / "data",
        demo=True,
    )

    assert settings.catalog_dir == packaged_catalog.resolve()


def test_settings_reads_rover_secret_at_the_configuration_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROVER_SECRET", "SYNTHETIC-ONLY-ROVER-SECRET")
    monkeypatch.setattr(config, "resolve_port", lambda *args, **kwargs: 8777)

    settings = config.Settings.from_environment(explicit_data_dir=tmp_path / "data")

    assert settings.rover_secret == "SYNTHETIC-ONLY-ROVER-SECRET"
