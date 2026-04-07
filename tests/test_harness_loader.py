from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from pipeline.harness_loader import (
    EvalCriteria,
    HarnessLoader,
    HarnessValidationError,
    IdentityBundle,
    LoadedHarness,
    WorkspaceConfig,
)


@pytest.fixture
def fixture_path() -> Path:
    return Path(__file__).parent / "fixtures" / "harness-fixture"


@pytest.fixture
def copied_fixture(fixture_path: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "harness"
    shutil.copytree(fixture_path, destination)
    return destination


def _set_testbot_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TESTBOT_SLACK_BOT_TOKEN", "xoxb-test-fixture")
    monkeypatch.setenv("TESTBOT_SLACK_APP_TOKEN", "xapp-test-fixture")


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def _mutate_yaml(
    path: Path,
    mutator: Callable[[Any], None],
    fallback: Callable[[str], str],
) -> None:
    try:
        from ruamel.yaml import YAML
    except ModuleNotFoundError:
        path.write_text(fallback(path.read_text()), encoding="utf-8")
        return

    yaml = YAML()
    data = yaml.load(path.read_text(encoding="utf-8"))
    mutator(data)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


def test_load_happy_path(fixture_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_testbot_env(monkeypatch)

    result = HarnessLoader.load(fixture_path)

    assert isinstance(result, LoadedHarness)
    assert result.slug == "testbot"
    assert result.bot_name == "TestBot"
    assert result.bot_token_env == "TESTBOT_SLACK_BOT_TOKEN"
    assert result.app_token_env == "TESTBOT_SLACK_APP_TOKEN"
    assert result.harness_path == fixture_path


def test_identity_bundle_content(
    fixture_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_testbot_env(monkeypatch)

    result = HarnessLoader.load(fixture_path)

    assert isinstance(result.identity, IdentityBundle)
    assert isinstance(result.identity.mission, str) and result.identity.mission.strip()
    assert isinstance(result.identity.brand, str) and result.identity.brand.strip()
    assert isinstance(result.identity.avatar, str) and result.identity.avatar.strip()
    assert isinstance(result.identity.never_list, str) and result.identity.never_list.strip()
    assert (
        isinstance(result.identity.bot_persona, str)
        and result.identity.bot_persona.strip()
    )


def test_eval_criteria_parsed(
    fixture_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_testbot_env(monkeypatch)

    result = HarnessLoader.load(fixture_path)

    assert isinstance(result.eval_criteria, EvalCriteria)
    assert result.eval_criteria.schema_version == 1
    assert result.eval_criteria.narrative.strip()
    assert result.eval_criteria.checks == []


def test_workspace_config_fully_populated(
    fixture_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_testbot_env(monkeypatch)

    result = HarnessLoader.load(fixture_path)

    assert isinstance(result.workspace, WorkspaceConfig)
    assert result.workspace.slug == "testbot"
    assert result.workspace.bot.display_name == "TestBot"
    assert result.workspace.limits.max_turns_per_session == 50
    assert result.workspace.channels.intake == "C00TESTINTAKE"
    assert "U00TEST00000" in result.workspace.access.allowed_user_ids
    assert result.workspace.deliverables.backend == "filesystem"


def test_resolve_path_env_var(
    fixture_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESS_PATH", str(fixture_path))

    resolved = HarnessLoader.resolve_path()

    assert isinstance(resolved, Path)
    assert resolved == fixture_path


def test_resolve_path_cli_flag_overrides_env(
    copied_fixture: Path, fixture_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESS_PATH", str(fixture_path))

    resolved = HarnessLoader.resolve_path(cli_flag=str(copied_fixture))

    assert resolved == copied_fixture


def test_resolve_path_neither_set_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARNESS_PATH", raising=False)

    with pytest.raises(
        HarnessValidationError,
        match=r"HARNESS_PATH environment variable is required",
    ):
        HarnessLoader.resolve_path()


def test_path_does_not_exist() -> None:
    with pytest.raises(
        HarnessValidationError,
        match=r"Harness path does not exist: /nonexistent/harness",
    ):
        HarnessLoader.load(Path("/nonexistent/harness"))


def test_path_is_not_a_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("plain file", encoding="utf-8")

    with pytest.raises(
        HarnessValidationError,
        match=r"Harness path is not a directory: .*",
    ):
        HarnessLoader.load(file_path)


def test_workspace_yaml_missing(copied_fixture: Path) -> None:
    _delete_path(copied_fixture / "workspace.yaml")

    with pytest.raises(
        HarnessValidationError,
        match=r"Required file missing: .*workspace\.yaml",
    ):
        HarnessLoader.load(copied_fixture)


def test_workspace_yaml_malformed(copied_fixture: Path) -> None:
    (copied_fixture / "workspace.yaml").write_text("{{{not valid yaml", encoding="utf-8")

    with pytest.raises(
        HarnessValidationError,
        match=r"workspace\.yaml parse error:",
    ):
        HarnessLoader.load(copied_fixture)


def test_workspace_yaml_bad_schema_version(copied_fixture: Path) -> None:
    workspace_yaml = copied_fixture / "workspace.yaml"
    _mutate_yaml(
        workspace_yaml,
        lambda data: data.__setitem__("schema_version", 99),
        lambda text: text.replace("schema_version: 1", "schema_version: 99"),
    )

    with pytest.raises(
        HarnessValidationError,
        match=r'workspace\.yaml invalid at field ".*schema_version.*"',
    ):
        HarnessLoader.load(copied_fixture)


def test_workspace_yaml_bad_slug(copied_fixture: Path) -> None:
    workspace_yaml = copied_fixture / "workspace.yaml"
    _mutate_yaml(
        workspace_yaml,
        lambda data: data.__setitem__("slug", "TestBot With Spaces"),
        lambda text: text.replace('slug: "testbot"', 'slug: "TestBot With Spaces"'),
    )

    with pytest.raises(
        HarnessValidationError,
        match=r'workspace\.yaml invalid at field ".*slug.*"',
    ):
        HarnessLoader.load(copied_fixture)


def test_workspace_yaml_missing_bot_display_name(copied_fixture: Path) -> None:
    workspace_yaml = copied_fixture / "workspace.yaml"
    _mutate_yaml(
        workspace_yaml,
        lambda data: data["bot"].pop("display_name"),
        lambda text: text.replace('  display_name: "TestBot"\n', ""),
    )

    with pytest.raises(
        HarnessValidationError,
        match=r'workspace\.yaml invalid at field ".*display_name.*"',
    ):
        HarnessLoader.load(copied_fixture)


def test_workspace_yaml_bad_channel_id(copied_fixture: Path) -> None:
    workspace_yaml = copied_fixture / "workspace.yaml"
    _mutate_yaml(
        workspace_yaml,
        lambda data: data["channels"].__setitem__("intake", "not-a-channel"),
        lambda text: text.replace('  intake: "C00TESTINTAKE"', '  intake: "not-a-channel"'),
    )

    with pytest.raises(
        HarnessValidationError,
        match=r'workspace\.yaml invalid at field ".*channels.*intake.*"',
    ):
        HarnessLoader.load(copied_fixture)


def test_workspace_yaml_empty_allowed_user_ids(copied_fixture: Path) -> None:
    workspace_yaml = copied_fixture / "workspace.yaml"
    _mutate_yaml(
        workspace_yaml,
        lambda data: data["access"].__setitem__("allowed_user_ids", []),
        lambda text: text.replace(
            'access:\n  allowed_user_ids:\n    - "U00TEST00000"\n',
            "access:\n  allowed_user_ids: []\n",
        ),
    )

    with pytest.raises(
        HarnessValidationError,
        match=r'workspace\.yaml invalid at field ".*access.*allowed_user_ids.*"',
    ):
        HarnessLoader.load(copied_fixture)


def test_workspace_yaml_negative_limit(copied_fixture: Path) -> None:
    workspace_yaml = copied_fixture / "workspace.yaml"
    _mutate_yaml(
        workspace_yaml,
        lambda data: data["limits"].__setitem__("max_turns_per_session", -1),
        lambda text: text.replace("  max_turns_per_session: 50", "  max_turns_per_session: -1"),
    )

    with pytest.raises(
        HarnessValidationError,
        match=r'workspace\.yaml invalid at field ".*limits.*max_turns_per_session.*"',
    ):
        HarnessLoader.load(copied_fixture)


def test_missing_identity_file(
    copied_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_testbot_env(monkeypatch)
    _delete_path(copied_fixture / "identity" / "brand.md")

    with pytest.raises(
        HarnessValidationError,
        match=r"Required identity file missing: .*/identity/brand\.md",
    ):
        HarnessLoader.load(copied_fixture)


def test_missing_eval_criteria(
    copied_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_testbot_env(monkeypatch)
    _delete_path(copied_fixture / "eval" / "criteria.yaml")

    with pytest.raises(
        HarnessValidationError,
        match=r"Required file missing: .*/eval/criteria\.yaml",
    ):
        HarnessLoader.load(copied_fixture)


def test_missing_required_directory(
    copied_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_testbot_env(monkeypatch)
    _delete_path(copied_fixture / "mechanic-log")

    with pytest.raises(
        HarnessValidationError,
        match=r"Required directory missing: .*/mechanic-log",
    ):
        HarnessLoader.load(copied_fixture)


def test_missing_vault_schema(
    copied_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_testbot_env(monkeypatch)
    _delete_path(copied_fixture / "vault" / "VAULT.md")

    with pytest.raises(
        HarnessValidationError,
        match=r"Required file missing: .*/vault/VAULT\.md",
    ):
        HarnessLoader.load(copied_fixture)


def test_missing_secret_env_var(
    fixture_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TESTBOT_SLACK_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TESTBOT_SLACK_APP_TOKEN", "xapp-test-fixture")

    with pytest.raises(
        HarnessValidationError,
        match=r"Required secret env var missing: TESTBOT_SLACK_BOT_TOKEN",
    ):
        HarnessLoader.load(fixture_path)
