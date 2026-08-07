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


def test_demo_and_normal_runs_use_distinct_data_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(config, "PACKAGE_ROOT", tmp_path / "site-packages" / "mycard_benefits")
    monkeypatch.setattr(config, "resolve_port", lambda *args, **kwargs: 8777)

    demo = config.Settings.from_environment(demo=True)
    normal = config.Settings.from_environment(demo=False)

    assert demo.data_dir == (tmp_path / "demo-data").resolve()
    assert normal.data_dir == (tmp_path / "data").resolve()
    assert demo.data_dir != normal.data_dir
    assert demo.demo is True
    assert normal.demo is False


def test_explicit_data_dir_still_wins_over_demo_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(config, "PACKAGE_ROOT", tmp_path / "site-packages" / "mycard_benefits")
    monkeypatch.setattr(config, "resolve_port", lambda *args, **kwargs: 8777)

    explicit = config.Settings.from_environment(
        explicit_data_dir=tmp_path / "elsewhere",
        demo=True,
    )

    assert explicit.data_dir == (tmp_path / "elsewhere").resolve()
