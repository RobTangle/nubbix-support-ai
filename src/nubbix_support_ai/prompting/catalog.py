import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nubbix_support_ai.support.contracts import AppError, SupportResponse


class CatalogError(AppError):
    pass


class VersionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    label: str = Field(min_length=1)


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1, le=1)
    default: str
    baseline: str
    versions: list[VersionInfo] = Field(min_length=1)


@dataclass(frozen=True)
class PromptBundle:
    version: str
    label: str
    system: str
    input_moderation: str
    output_moderation: str
    repair: str
    examples: tuple[tuple[str, str], ...]
    content_hash: str
    comparison_hash: str


class PromptCatalog:
    def __init__(self, registry: Registry, bundles: dict[str, PromptBundle]) -> None:
        self.default = registry.default
        self.baseline = registry.baseline
        self.versions = tuple(registry.versions)
        self._bundles = bundles

    def get(self, version: str | None = None) -> PromptBundle:
        try:
            return self._bundles[version or self.default]
        except KeyError:
            raise CatalogError("unknown_prompt_version") from None


def _read_yaml(path: Path, boundary: Path) -> dict[str, Any]:
    if not path.resolve().is_relative_to(boundary.resolve()):
        raise CatalogError("unsafe_prompt_path")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CatalogError("invalid_prompt_resource")
    return value


def load_catalog(project_root: Path) -> PromptCatalog:
    try:
        root = project_root / "prompts"
        registry = Registry.model_validate(_read_yaml(root / "registry.yaml", root))
        ids = [item.id for item in registry.versions]
        if len(set(ids)) != len(ids) or registry.default not in ids or registry.baseline not in ids:
            raise CatalogError("invalid_prompt_registry")
        bundles = {}
        for item in registry.versions:
            directory = root / "versions" / item.id
            if not directory.resolve().is_relative_to(root.resolve()):
                raise CatalogError("unsafe_prompt_path")
            context = _read_yaml(directory / "context.yaml", directory)["manual"]
            system = _read_yaml(directory / "system.yaml", directory)["instructions"]
            safety = _read_yaml(directory / "safety.yaml", directory)
            texts = [system, safety["input_moderation"], safety["output_moderation"]]
            if not isinstance(context, str) or not context.strip():
                raise CatalogError("empty_prompt_context")
            if any(not isinstance(text, str) or "{{manual}}" not in text for text in texts):
                raise CatalogError("missing_manual_placeholder")
            compiled = [text.replace("{{manual}}", context) for text in texts]
            repair = safety["repair"]
            if not isinstance(repair, str) or not repair.strip():
                raise CatalogError("empty_repair_prompt")
            if any(re.search(r"\{\{|\}\}", text) for text in [*compiled, repair]):
                raise CatalogError("unresolved_prompt_placeholder")
            examples: list[tuple[str, str]] = []
            examples_path = directory / "examples.yaml"
            if examples_path.exists():
                for example in _read_yaml(examples_path, directory)["examples"]:
                    ticket = example["ticket"]
                    if not isinstance(ticket, str) or not ticket.strip():
                        raise CatalogError("invalid_few_shot_ticket")
                    response = SupportResponse.model_validate(example["response"])
                    examples.append((ticket, response.model_dump_json()))
            common = json.dumps([*compiled, repair], ensure_ascii=False, sort_keys=True)
            effective = json.dumps([item.id, common, examples], ensure_ascii=False)
            bundles[item.id] = PromptBundle(
                item.id, item.label, compiled[0], compiled[1], compiled[2], repair, tuple(examples),
                hashlib.sha256(effective.encode()).hexdigest(),
                hashlib.sha256(common.encode()).hexdigest(),
            )
        return PromptCatalog(registry, bundles)
    except CatalogError:
        raise
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError, ValidationError):
        raise CatalogError("invalid_prompt_catalog") from None
