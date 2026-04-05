from __future__ import annotations

import json
import os
import re
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..common.constants import ADDON_CONSTANTS

SUPPORTED_MEDIA_EXTENSIONS = {".gif", ".webm", ".mp4"}
PACKAGED_DEFAULT_SOURCE_FOLDER_NAME = "Wallpapers_anki"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "tutorial_seen": True,
    "theme_mode": "dark",
    "targets": {
        "reviewer": True,
        "deck_browser": True,
        "main_window": False,
    },
    "media": {
        "selected_file": "",
        "source_folder": "",
        "trim_start": 0.0,
        "trim_end": 0.0,
        "opacity": 0.35,
        "blur": 0,
        "zoom": 1.0,
        "muted": True,
        "playback_rate": 1.0,
    },
}


def _deep_merge_dicts(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)

    for key, value in overrides.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = deepcopy(value)

    return merged


def _sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    return cleaned or "background"


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _clamp_float(value: object, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _clamp_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


class ConfigManager:
    def __init__(self, addon_root: str | Path | None = None) -> None:
        self.addon_root = Path(addon_root).resolve() if addon_root else Path(__file__).resolve().parents[2]
        self.user_files_dir = self.addon_root / ADDON_CONSTANTS.USER_FILES_DIRECTORY_NAME.value
        self.media_dir = self.user_files_dir / ADDON_CONSTANTS.MEDIA_DIRECTORY_NAME.value
        self.config_path = self.user_files_dir / ADDON_CONSTANTS.CONFIG_FILENAME.value
        self._runtime_media_override: Path | None = None
        self.data: dict[str, Any] = deepcopy(DEFAULT_CONFIG)
        self.reload()

    def reload(self) -> dict[str, Any]:
        loaded: dict[str, Any] = {}

        if self.config_path.exists():
            try:
                with self.config_path.open("r", encoding="utf-8") as config_file:
                    raw_data = json.load(config_file)
                if isinstance(raw_data, dict):
                    loaded = raw_data
            except (json.JSONDecodeError, OSError):
                loaded = {}

        if loaded:
            raw_data = _deep_merge_dicts(DEFAULT_CONFIG, loaded)
        else:
            raw_data = self.default_data()

        self.data = self.normalize_data(raw_data)
        self._normalize_media_selection()
        self.clear_runtime_media_override()
        return self.data

    def default_data(self) -> dict[str, Any]:
        default_data = deepcopy(DEFAULT_CONFIG)
        packaged_folder = self.packaged_default_source_folder()
        if packaged_folder is None:
            return default_data

        default_data["media"]["source_folder"] = self.serialize_source_folder(packaged_folder)
        return default_data

    def normalize_data(self, data: dict[str, Any] | None) -> dict[str, Any]:
        merged = _deep_merge_dicts(DEFAULT_CONFIG, data if isinstance(data, dict) else {})
        targets = merged.get("targets", {})

        normalized = {
            "enabled": _coerce_bool(merged.get("enabled", True), True),
            "tutorial_seen": True,
            "theme_mode": "light" if merged.get("theme_mode") == "light" else "dark",
            "targets": {
                "reviewer": _coerce_bool(targets.get("reviewer", True), True),
                "deck_browser": _coerce_bool(targets.get("deck_browser", True), True),
                "main_window": _coerce_bool(targets.get("main_window", False), False),
            },
            "media": self.normalize_media_config(merged.get("media", {})),
        }
        return normalized

    def normalize_media_config(self, media_config: Any) -> dict[str, Any]:
        media = media_config if isinstance(media_config, dict) else {}
        source_folder = media.get("source_folder", "")
        if not isinstance(source_folder, str):
            source_folder = ""
        elif source_folder:
            resolved_source_folder = self.resolve_source_folder(source_folder)
            if resolved_source_folder is None:
                source_folder = ""
            else:
                source_folder = self.serialize_source_folder(resolved_source_folder)

        trim_start = _clamp_float(media.get("trim_start", 0.0), 0.0, 0.0, 86_400.0)
        trim_end = _clamp_float(media.get("trim_end", 0.0), 0.0, 0.0, 86_400.0)
        if trim_end > 0 and trim_end < trim_start:
            trim_end = trim_start

        return {
            "selected_file": media.get("selected_file", "")
            if isinstance(media.get("selected_file", ""), str)
            else "",
            "source_folder": source_folder,
            "trim_start": trim_start,
            "trim_end": trim_end,
            "opacity": _clamp_float(media.get("opacity", 0.35), 0.35, 0.0, 1.0),
            "blur": _clamp_int(media.get("blur", 0), 0, 0, 24),
            "zoom": _clamp_float(media.get("zoom", 1.0), 1.0, 1.0, 1.6),
            "muted": _coerce_bool(media.get("muted", True), True),
            "playback_rate": _clamp_float(media.get("playback_rate", 1.0), 1.0, 0.25, 3.0),
        }

    def save(self) -> None:
        self.user_files_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        payload = self.normalize_data(self.data)

        with self.config_path.open("w", encoding="utf-8") as config_file:
            json.dump(payload, config_file, indent=2)
            config_file.write("\n")

        self.data = payload
        self._normalize_media_selection()
        self.clear_runtime_media_override()

    def restore_defaults(self) -> dict[str, Any]:
        self.data = self.normalize_data(self.default_data())
        self._normalize_media_selection()
        self.clear_runtime_media_override()
        self.save()
        return self.data

    def reset_to_defaults(self) -> list[str]:
        self.restore_defaults()
        return self.remove_managed_media_files()

    def list_media_files(self) -> list[str]:
        self.media_dir.mkdir(parents=True, exist_ok=True)
        return sorted(
            path.name
            for path in self.media_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS
        )

    def list_source_folder_files(self, folder: str) -> list[str]:
        if not folder:
            return []

        source_dir = self.resolve_source_folder(folder)
        if source_dir is None:
            return []

        return sorted(
            str(path.relative_to(source_dir))
            for path in source_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS
        )

    def resolve_source_folder_media_path(self, folder: str, selected_file: str) -> Path | None:
        if not folder or not selected_file:
            return None

        source_dir = self.resolve_source_folder(folder)
        if source_dir is None:
            return None

        candidate = (source_dir / selected_file).resolve()
        try:
            candidate.relative_to(source_dir)
        except ValueError:
            return None

        return candidate if candidate.is_file() else None

    def import_media(self, source_path: str) -> str:
        return self.commit_media_from_path(source_path)

    def commit_media_from_path(self, source_path: str | Path) -> str:
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError("Selected media file was not found.")

        extension = source.suffix.lower()
        if extension not in SUPPORTED_MEDIA_EXTENSIONS:
            raise ValueError("Supported formats: gif, webm, mp4.")

        self.media_dir.mkdir(parents=True, exist_ok=True)
        existing_match = self._find_existing_managed_match(source)
        if existing_match is not None:
            self.data.setdefault("media", {})["selected_file"] = existing_match.name
            return existing_match.name

        temp_destination = self._temporary_media_path(extension)
        try:
            try:
                os.link(source, temp_destination)
            except OSError:
                shutil.copy2(source, temp_destination)

            destination = self._unique_media_path(_sanitize_filename(source.stem), extension)
            os.replace(temp_destination, destination)
        except Exception:
            temp_destination.unlink(missing_ok=True)
            raise

        self.data.setdefault("media", {})["selected_file"] = destination.name
        return destination.name

    def media_path(self, filename: str) -> Path:
        return self.media_dir / filename

    def source_folder_is_inside_media_dir(self, folder: str) -> bool:
        if not folder:
            return False
        try:
            resolved_folder = self.resolve_source_folder(folder)
            if resolved_folder is None:
                return False
            resolved_folder.relative_to(self.media_dir.resolve())
        except ValueError:
            return False
        return True

    def resolve_source_folder(self, folder: str | Path) -> Path | None:
        candidate = Path(folder).expanduser()
        if not candidate.is_absolute():
            candidate = self.addon_root / candidate
        resolved = candidate.resolve()
        return resolved if resolved.is_dir() else None

    def serialize_source_folder(self, folder: str | Path) -> str:
        resolved = Path(folder).expanduser().resolve()
        try:
            return str(resolved.relative_to(self.addon_root))
        except ValueError:
            return str(resolved)

    def packaged_default_source_folder(self) -> Path | None:
        candidate = self.media_dir / PACKAGED_DEFAULT_SOURCE_FOLDER_NAME
        if not candidate.is_dir():
            return None
        return candidate.resolve() if self.list_source_folder_files(str(candidate)) else None

    def set_runtime_media_override(self, media_path: str | Path | None) -> None:
        if media_path is None:
            self._runtime_media_override = None
            return
        resolved = Path(media_path).expanduser().resolve()
        self._runtime_media_override = resolved if resolved.is_file() else None

    def clear_runtime_media_override(self) -> None:
        self._runtime_media_override = None

    def runtime_media_override(self) -> Path | None:
        return self._runtime_media_override

    def resolve_media_path(self, media_config: dict[str, Any] | None = None) -> Path | None:
        if self._runtime_media_override is not None and self._runtime_media_override.is_file():
            return self._runtime_media_override

        resolved_media_config = media_config or self.data.get("media", {})
        selected_file = resolved_media_config.get("selected_file", "")
        if not isinstance(selected_file, str) or not selected_file:
            return None

        source_folder = resolved_media_config.get("source_folder", "")
        if isinstance(source_folder, str) and source_folder:
            source_path = self.resolve_source_folder_media_path(source_folder, selected_file)
            if source_path is not None and source_path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS:
                return source_path

        managed_path = self.media_path(selected_file)
        if managed_path.is_file() and managed_path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS:
            return managed_path.resolve()
        return None

    def _temporary_media_path(self, extension: str) -> Path:
        index = 0
        while True:
            candidate = self.media_dir / f".import-{os.getpid()}-{index}{extension}"
            if not candidate.exists():
                return candidate
            index += 1

    def _find_existing_managed_match(self, source_path: Path) -> Path | None:
        for filename in self.list_media_files():
            candidate = self.media_path(filename)
            try:
                if os.path.samefile(source_path, candidate):
                    return candidate
            except OSError:
                continue
        return None

    def _unique_media_path(self, base_name: str, extension: str) -> Path:
        candidate = self.media_dir / f"{base_name}{extension}"
        index = 1
        while candidate.exists():
            candidate = self.media_dir / f"{base_name}-{index}{extension}"
            index += 1
        return candidate

    def _normalize_media_selection(self) -> None:
        media_config = self.data.setdefault("media", self.normalize_media_config({}))
        source_folder = str(media_config.get("source_folder", ""))
        selected = media_config.get("selected_file", "")
        if source_folder:
            files = self.list_source_folder_files(source_folder)
            if selected and selected in files:
                return
            media_config["selected_file"] = ""
            return

        files = self.list_media_files()
        if selected and selected in files:
            return
        media_config["selected_file"] = ""

    def remove_managed_media_files(self) -> list[str]:
        if not self.media_dir.exists():
            return []

        failed_removals: list[str] = []
        for path in self.media_dir.iterdir():
            if path.is_file():
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    failed_removals.append(path.name)
        return failed_removals
