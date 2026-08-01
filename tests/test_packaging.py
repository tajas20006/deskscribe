import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def test_project_is_licensed_under_mit() -> None:
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    distribution_guide = (PROJECT_ROOT / "WINDOWS_DISTRIBUTION.md").read_text(
        encoding="utf-8"
    )

    assert project["project"]["license"] == "MIT"
    assert "Copyright (c) 2026 Shun Yoshioka" in license_text
    assert "Permission is hereby granted, free of charge" in license_text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in license_text
    assert "[MIT License](LICENSE)" in readme
    assert "`LICENSE`" in distribution_guide


def test_pyinstaller_is_a_development_dependency() -> None:
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    dependencies = project["dependency-groups"]["dev"]

    assert any(dependency.startswith("pyinstaller>=") for dependency in dependencies)


def test_windows_spec_builds_a_windowed_executable_without_user_data() -> None:
    spec = (PROJECT_ROOT / "packaging" / "windows" / "DeskScribe.spec").read_text(
        encoding="utf-8"
    )

    assert 'name="DeskScribe"' in spec
    assert "console=False" in spec
    for excluded in ("models", "tests", ".agents", ".venv", ".uv-cache"):
        assert excluded in spec


def test_build_script_packages_executable_in_a_checksummed_zip() -> None:
    script = (PROJECT_ROOT / "scripts" / "build_windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "DeskScribe.spec" in script
    assert 'Copy-Item -LiteralPath "LICENSE" -Destination $releaseDir' in script
    assert "THIRD_PARTY_LICENSES.md" in script
    assert "WINDOWS_DISTRIBUTION.md" in script
    assert "Compress-Archive" in script
    assert "Get-FileHash" in script


def test_distribution_guide_keeps_whisper_model_external() -> None:
    guide = (PROJECT_ROOT / "WINDOWS_DISTRIBUTION.md").read_text(encoding="utf-8")

    assert "DeskScribe.exe" in guide
    assert "モデル" in guide
    assert "同梱されていません" in guide
