"""Load and validate an external harness repository into typed runtime models."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, ValidationError

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError
except ModuleNotFoundError:
    import yaml as pyyaml

    YAML = None
    YAMLError = pyyaml.YAMLError


SLUG_PATTERN = r"^[a-z0-9-]+$"
SLACK_CHANNEL_PATTERN = r"^C[A-Z0-9]{8,}$"


class HarnessValidationError(Exception):
    """Raised when a harness fails to load. Always names path + field."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BotConfig(_FrozenModel):
    display_name: str = Field(min_length=1)
    avatar_path: Optional[str] = None
    slack_app_id: Optional[str] = None
    slack_bot_token_env: str = Field(min_length=1)
    slack_app_token_env: str = Field(min_length=1)


class GitConfig(_FrozenModel):
    user_name: str = Field(min_length=1)
    user_email: str = Field(min_length=1)
    github_token_env: Optional[str] = None
    github_username: Optional[str] = None


class ChannelsConfig(_FrozenModel):
    intake: str = Field(pattern=SLACK_CHANNEL_PATTERN)
    factory_floor: str = Field(pattern=SLACK_CHANNEL_PATTERN)
    mechanic_log: str = Field(pattern=SLACK_CHANNEL_PATTERN)
    brand_assets: str = Field(pattern=SLACK_CHANNEL_PATTERN)


class AccessConfig(_FrozenModel):
    allowed_user_ids: list[str] = Field(min_length=1)


class LimitsConfig(_FrozenModel):
    max_concurrent_sessions: PositiveInt
    max_budget_usd_per_session: PositiveFloat
    max_budget_usd_per_day: PositiveFloat
    max_turns_per_session: PositiveInt
    session_idle_timeout_seconds: PositiveInt
    worker_timeout_seconds: PositiveInt
    mechanic_timeout_seconds: PositiveInt


class FilesystemDeliverableConfig(_FrozenModel):
    path: str = Field(min_length=1)


class DeliverablesConfig(_FrozenModel):
    backend: Literal["filesystem"]
    filesystem: FilesystemDeliverableConfig


class WorkspaceConfig(_FrozenModel):
    schema_version: Literal[1]
    slug: str = Field(pattern=SLUG_PATTERN, max_length=32)
    bot: BotConfig
    git: GitConfig
    channels: ChannelsConfig
    access: AccessConfig
    limits: LimitsConfig
    deliverables: DeliverablesConfig


class EvalCheck(_FrozenModel):
    id: str
    description: str
    type: Literal["llm_judge", "regex", "url_check", "length", "custom"]
    pattern: Optional[str] = None
    must_not_match: Optional[bool] = None


class EvalCriteria(_FrozenModel):
    schema_version: Literal[1]
    narrative: str
    checks: list[EvalCheck] = Field(default_factory=list)


@dataclass(frozen=True)
class IdentityBundle:
    mission: str
    brand: str
    avatar: str
    never_list: str
    bot_persona: str


@dataclass(frozen=True)
class LoadedHarness:
    harness_path: Path
    workspace: WorkspaceConfig
    identity: IdentityBundle
    eval_criteria: EvalCriteria

    @property
    def slug(self) -> str:
        return self.workspace.slug

    @property
    def bot_name(self) -> str:
        return self.workspace.bot.display_name

    @property
    def bot_token_env(self) -> str:
        return self.workspace.bot.slack_bot_token_env

    @property
    def app_token_env(self) -> str:
        return self.workspace.bot.slack_app_token_env


class HarnessLoader:
    @staticmethod
    def resolve_path(cli_flag: str | Path | None = None) -> Path:
        if cli_flag is not None and cli_flag != "":
            return Path(cli_flag).resolve()

        env_path = os.environ.get("HARNESS_PATH")
        if env_path:
            return Path(env_path).resolve()

        raise HarnessValidationError(
            "HARNESS_PATH environment variable is required. Set it to an absolute path to a harness repository."
        )

    @staticmethod
    def load(harness_path: Path | str) -> LoadedHarness:
        path = Path(harness_path)

        if not path.exists():
            raise HarnessValidationError(f"Harness path does not exist: {path}")
        if not path.is_dir():
            raise HarnessValidationError(f"Harness path is not a directory: {path}")

        workspace_path = path / "workspace.yaml"
        if not workspace_path.is_file():
            raise HarnessValidationError(f"Required file missing: {workspace_path}")

        workspace_data = HarnessLoader._load_yaml_file(
            workspace_path, "workspace.yaml parse error"
        )
        workspace = HarnessLoader._validate_model(
            workspace_data,
            WorkspaceConfig,
            "workspace.yaml",
        )

        HarnessLoader._require_env_var(
            workspace.bot.slack_bot_token_env,
            "bot.slack_bot_token_env",
        )
        HarnessLoader._require_env_var(
            workspace.bot.slack_app_token_env,
            "bot.slack_app_token_env",
        )

        for relative_dir in (
            "identity",
            "eval",
            "skills",
            "mechanic-log",
            "vault",
            "vault/raw",
            "vault/summaries",
            "vault/summaries/sources",
            "vault/summaries/sessions",
            "vault/entities",
            "vault/concepts",
            "vault/decisions",
        ):
            required_dir = path / relative_dir
            if not required_dir.is_dir():
                raise HarnessValidationError(f"Required directory missing: {required_dir}")

        identity_files = {
            "mission": path / "identity" / "mission.md",
            "brand": path / "identity" / "brand.md",
            "avatar": path / "identity" / "avatar.md",
            "never_list": path / "identity" / "never-list.md",
            "bot_persona": path / "identity" / "bot-persona.md",
        }
        for identity_path in identity_files.values():
            if not identity_path.is_file():
                raise HarnessValidationError(
                    f"Required identity file missing: {identity_path}"
                )

        eval_path = path / "eval" / "criteria.yaml"
        if not eval_path.is_file():
            raise HarnessValidationError(f"Required file missing: {eval_path}")

        for relative_file in ("vault/VAULT.md", "vault/index.md", "vault/log.md"):
            required_file = path / relative_file
            if not required_file.is_file():
                raise HarnessValidationError(f"Required file missing: {required_file}")

        identity = IdentityBundle(
            mission=identity_files["mission"].read_text(encoding="utf-8"),
            brand=identity_files["brand"].read_text(encoding="utf-8"),
            avatar=identity_files["avatar"].read_text(encoding="utf-8"),
            never_list=identity_files["never_list"].read_text(encoding="utf-8"),
            bot_persona=identity_files["bot_persona"].read_text(encoding="utf-8"),
        )

        eval_data = HarnessLoader._load_yaml_file(
            eval_path, "eval/criteria.yaml parse error"
        )
        eval_criteria = HarnessLoader._validate_model(
            eval_data,
            EvalCriteria,
            "eval/criteria.yaml",
        )

        return LoadedHarness(
            harness_path=path,
            workspace=workspace,
            identity=identity,
            eval_criteria=eval_criteria,
        )

    @staticmethod
    def _load_yaml_file(path: Path, error_prefix: str) -> Any:
        try:
            with path.open("r", encoding="utf-8") as handle:
                if YAML is not None:
                    return YAML(typ="safe").load(handle)
                return pyyaml.safe_load(handle)
        except YAMLError as exc:
            raise HarnessValidationError(f"{error_prefix}: {exc}") from exc

    @staticmethod
    def _validate_model(data: Any, model: type[_FrozenModel], source_name: str) -> Any:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            error = exc.errors()[0]
            field_path = HarnessLoader._format_field_path(error.get("loc", ()))
            reason = error.get("msg", "Validation failed")
            expected = HarnessLoader._format_expected(error)
            got = error.get("input")
            raise HarnessValidationError(
                f'{source_name} invalid at field "{field_path}": {reason}. '
                f"Expected: {expected}. Got: {got!r}."
            ) from exc

    @staticmethod
    def _format_field_path(location: tuple[Any, ...]) -> str:
        if not location:
            return "<root>"

        parts: list[str] = []
        for item in location:
            if isinstance(item, int):
                if parts:
                    parts[-1] = f"{parts[-1]}[{item}]"
                else:
                    parts.append(f"[{item}]")
            else:
                parts.append(str(item))
        return ".".join(parts)

    @staticmethod
    def _format_expected(error: dict[str, Any]) -> str:
        error_type = error.get("type")
        ctx = error.get("ctx", {})

        if "expected" in ctx:
            return str(ctx["expected"])
        if "pattern" in ctx:
            return f"pattern {ctx['pattern']!r}"
        if "min_length" in ctx:
            return f"minimum length {ctx['min_length']}"
        if "gt" in ctx:
            return f"> {ctx['gt']}"
        if error_type == "missing":
            return "field present"
        if error_type == "extra_forbidden":
            return "no extra fields"
        return "valid value"

    @staticmethod
    def _require_env_var(env_var_name: str, workspace_field: str) -> None:
        if env_var_name not in os.environ:
            raise HarnessValidationError(
                f"Required secret env var missing: {env_var_name} "
                f"(referenced by workspace.yaml {workspace_field})"
            )
