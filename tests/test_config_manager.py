from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.config.config_manager import ConfigManager, SUPPORTED_MEDIA_EXTENSIONS

MINIMAL_GIF = (
    b"GIF89a"
    b"\x01\x00\x01\x00"
    b"\x80\x00\x00"
    b"\x00\x00\x00"
    b"\xff\xff\xff"
    b"!\xf9\x04\x01\x00\x00\x00\x00"
    b",\x00\x00\x00\x00\x01\x00\x01\x00\x00"
    b"\x02\x02D\x01\x00"
    b";"
)


class ConfigManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def _write_media(self, path: Path, *, payload: bytes = MINIMAL_GIF) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def test_reload_normalizes_invalid_config_and_drops_legacy_fields_on_save(self) -> None:
        user_files = self.root / "user_files"
        user_files.mkdir(parents=True, exist_ok=True)
        (user_files / "config.json").write_text(
            json.dumps(
                {
                    "enabled": "yes",
                    "tutorial_seen": "no",
                    "theme_mode": "banana",
                    "targets": {
                        "reviewer": "false",
                        "deck_browser": 0,
                        "main_window": "true",
                    },
                    "media": {
                        "selected_file": "demo.png",
                        "source_folder": 42,
                        "source_url": "https://legacy.example/test.png",
                        "trim_start": "oops",
                        "trim_end": "1.25",
                        "opacity": "1.7",
                        "blur": "-5",
                        "zoom": "0.5",
                        "muted": "false",
                        "bounce": True,
                        "playback_rate": "9.0",
                    },
                }
            ),
            encoding="utf-8",
        )

        manager = ConfigManager(addon_root=self.root)

        self.assertTrue(manager.data["enabled"])
        self.assertTrue(manager.data["tutorial_seen"])
        self.assertEqual(manager.data["theme_mode"], "dark")
        self.assertFalse(manager.data["targets"]["reviewer"])
        self.assertFalse(manager.data["targets"]["deck_browser"])
        self.assertTrue(manager.data["targets"]["main_window"])
        self.assertEqual(manager.data["media"]["source_folder"], "")
        self.assertEqual(manager.data["media"]["selected_file"], "")
        self.assertEqual(manager.data["media"]["trim_start"], 0.0)
        self.assertEqual(manager.data["media"]["trim_end"], 1.25)
        self.assertEqual(manager.data["media"]["opacity"], 1.0)
        self.assertEqual(manager.data["media"]["blur"], 0)
        self.assertEqual(manager.data["media"]["zoom"], 1.0)
        self.assertFalse(manager.data["media"]["muted"])
        self.assertEqual(manager.data["media"]["playback_rate"], 3.0)
        self.assertNotIn("bounce", manager.data["media"])

        manager.save()
        persisted = json.loads((user_files / "config.json").read_text(encoding="utf-8"))
        self.assertNotIn("source_url", persisted["media"])
        self.assertNotIn("bounce", persisted["media"])

    def test_commit_media_accepts_only_supported_formats(self) -> None:
        source = self.root / "clip.gif"
        self._write_media(source)
        manager = ConfigManager(addon_root=self.root / "supported-root")

        committed_name = manager.commit_media_from_path(source)

        self.assertEqual(Path(committed_name).suffix.lower(), ".gif")
        self.assertTrue(manager.media_path(committed_name).is_file())
        self.assertEqual(SUPPORTED_MEDIA_EXTENSIONS, {".gif", ".webm", ".mp4"})

        png_source = self.root / "still.png"
        self._write_media(png_source)
        with self.assertRaisesRegex(ValueError, "gif, webm, mp4"):
            manager.commit_media_from_path(png_source)

    def test_profile_folder_uses_profile_addon_data_directory(self) -> None:
        profile_folder = self.root / "profile"

        manager = ConfigManager(addon_root=self.root / "addon", profile_folder=profile_folder)

        self.assertEqual(
            manager.user_files_dir,
            profile_folder / "addon_data" / "AnkiAnimatedBackground",
        )
        self.assertEqual(manager.config_path, manager.user_files_dir / "config.json")

    def test_without_profile_folder_falls_back_to_addon_user_files(self) -> None:
        addon_root = self.root / "addon"

        manager = ConfigManager(addon_root=addon_root)

        self.assertEqual(manager.user_files_dir, addon_root / "user_files")

    def test_reload_switches_to_profile_data_when_profile_becomes_available(self) -> None:
        addon_root = self.root / "addon"
        profile_folder = self.root / "profile"
        manager = ConfigManager(addon_root=addon_root)

        with mock.patch.object(manager, "_resolve_profile_folder", return_value=profile_folder):
            manager.reload()

        self.assertEqual(
            manager.user_files_dir,
            profile_folder / "addon_data" / "AnkiAnimatedBackground",
        )

    def test_migrates_legacy_config_and_imported_media_to_profile_data(self) -> None:
        addon_root = self.root / "addon"
        profile_folder = self.root / "profile"
        legacy_user_files = addon_root / "user_files"
        legacy_media = legacy_user_files / "media"
        packaged_default = addon_root / "assets" / "default_media" / "Wallpapers_anki" / "Smoke"
        self._write_media(packaged_default / "default.gif")
        self._write_media(legacy_media / "custom.gif")
        self._write_media(legacy_media / "Wallpapers_anki" / "Smoke" / "legacy-default.gif")
        legacy_user_files.mkdir(parents=True, exist_ok=True)
        (legacy_user_files / "config.json").write_text(
            json.dumps(
                {
                    "media": {
                        "source_folder": str(Path("user_files") / "media" / "Wallpapers_anki"),
                        "selected_file": "",
                    }
                }
            ),
            encoding="utf-8",
        )

        manager = ConfigManager(addon_root=addon_root, profile_folder=profile_folder)

        self.assertEqual(
            manager.data["media"]["source_folder"],
            str(Path("assets") / "default_media" / "Wallpapers_anki"),
        )
        self.assertTrue((manager.media_dir / "custom.gif").is_file())
        self.assertFalse((manager.media_dir / "Wallpapers_anki" / "Smoke" / "legacy-default.gif").exists())
        self.assertFalse(legacy_user_files.exists())
        self.assertTrue((addon_root / "user_files_migrated").exists())

    def test_legacy_cleanup_failure_is_non_fatal_and_retried_later(self) -> None:
        addon_root = self.root / "addon"
        profile_folder = self.root / "profile"
        legacy_user_files = addon_root / "user_files"
        legacy_user_files.mkdir(parents=True, exist_ok=True)
        (legacy_user_files / "config.json").write_text("{}", encoding="utf-8")

        with mock.patch("pathlib.Path.rename", side_effect=PermissionError("locked")):
            manager = ConfigManager(addon_root=addon_root, profile_folder=profile_folder)

        self.assertIn("locked", manager.last_migration_error or "")
        self.assertTrue(legacy_user_files.exists())
        self.assertTrue(manager.config_path.is_file())

    def test_commit_media_prefers_link_then_copy_fallback(self) -> None:
        source = self.root / "source.gif"
        self._write_media(source)

        linked_manager = ConfigManager(addon_root=self.root / "link-root")
        with mock.patch("src.config.config_manager.os.link") as mocked_link:
            mocked_link.side_effect = lambda src, dst: shutil.copy2(src, dst)
            committed_name = linked_manager.commit_media_from_path(source)
        self.assertTrue(mocked_link.called)
        self.assertTrue(linked_manager.media_path(committed_name).is_file())

        copied_manager = ConfigManager(addon_root=self.root / "copy-root")
        with (
            mock.patch("src.config.config_manager.os.link", side_effect=OSError("cross-device")),
            mock.patch("src.config.config_manager.shutil.copy2", wraps=shutil.copy2) as mocked_copy,
        ):
            copied_name = copied_manager.commit_media_from_path(source)
        self.assertTrue(mocked_copy.called)
        self.assertTrue(copied_manager.media_path(copied_name).is_file())

    def test_commit_media_reuses_existing_match(self) -> None:
        source = self.root / "reuse.gif"
        self._write_media(source)

        manager = ConfigManager(addon_root=self.root / "reuse-root")
        first_name = manager.commit_media_from_path(source)
        second_name = manager.commit_media_from_path(source)

        self.assertEqual(first_name, second_name)
        self.assertEqual(manager.list_media_files(), [first_name])

    def test_list_source_folder_files_recurses_and_returns_relative_paths(self) -> None:
        source_dir = self.root / "wallpapers"
        self._write_media(source_dir / "root.gif")
        self._write_media(source_dir / "anime" / "loop.webm", payload=b"webm")
        self._write_media(source_dir / "nature" / "forest" / "loop.mp4", payload=b"mp4")
        self._write_media(source_dir / "ignored.png")

        manager = ConfigManager(addon_root=self.root / "scan-root")

        self.assertEqual(
            manager.list_source_folder_files(str(source_dir)),
            [
                str(Path("anime") / "loop.webm"),
                str(Path("nature") / "forest" / "loop.mp4"),
                "root.gif",
            ],
        )

    def test_resolve_source_folder_media_path_rejects_escape_paths(self) -> None:
        source_dir = self.root / "wallpapers"
        self._write_media(source_dir / "safe.gif")
        outside_file = self.root / "outside.gif"
        self._write_media(outside_file)

        manager = ConfigManager(addon_root=self.root / "resolve-root")

        self.assertEqual(
            manager.resolve_source_folder_media_path(str(source_dir), "safe.gif"),
            (source_dir / "safe.gif").resolve(),
        )
        self.assertIsNone(
            manager.resolve_source_folder_media_path(str(source_dir), str(Path("..") / "outside.gif"))
        )

    def test_first_reload_defaults_to_packaged_folder_with_none_selection(self) -> None:
        default_source = self.root / "assets" / "default_media" / "Wallpapers_anki" / "Smoke"
        self._write_media(default_source / "default.gif")

        manager = ConfigManager(addon_root=self.root)

        self.assertEqual(
            manager.data["media"]["source_folder"], str(Path("assets") / "default_media" / "Wallpapers_anki")
        )
        self.assertEqual(manager.data["media"]["selected_file"], "")

    def test_reset_to_defaults_restores_packaged_folder_and_clears_imported_media(self) -> None:
        packaged_source = self.root / "assets" / "default_media" / "Wallpapers_anki" / "Smoke"
        self._write_media(packaged_source / "default.gif")
        imported_source = self.root / "custom.gif"
        self._write_media(imported_source)

        manager = ConfigManager(addon_root=self.root)
        managed_name = manager.commit_media_from_path(imported_source)
        manager.data["media"]["source_folder"] = ""
        manager.data["media"]["selected_file"] = managed_name
        manager.save()

        failed_removals = manager.reset_to_defaults()

        self.assertEqual(failed_removals, [])
        self.assertEqual(
            manager.data["media"]["source_folder"], str(Path("assets") / "default_media" / "Wallpapers_anki")
        )
        self.assertEqual(manager.data["media"]["selected_file"], "")
        self.assertFalse(manager.media_path(managed_name).exists())

    def test_reset_to_defaults_reports_locked_managed_files_without_crashing(self) -> None:
        packaged_source = self.root / "assets" / "default_media" / "Wallpapers_anki" / "Smoke"
        self._write_media(packaged_source / "default.gif")
        imported_source = self.root / "custom.gif"
        self._write_media(imported_source)

        manager = ConfigManager(addon_root=self.root)
        managed_name = manager.commit_media_from_path(imported_source)

        with mock.patch("pathlib.Path.unlink", side_effect=PermissionError("locked")):
            failed_removals = manager.reset_to_defaults()

        self.assertEqual(failed_removals, [managed_name])
        self.assertEqual(manager.data["media"]["selected_file"], "")

    def test_serialize_and_resolve_packaged_source_folder_as_addon_relative_path(self) -> None:
        packaged_root = self.root / "assets" / "default_media" / "Wallpapers_anki"
        packaged_root.mkdir(parents=True, exist_ok=True)
        manager = ConfigManager(addon_root=self.root)

        serialized = manager.serialize_source_folder(packaged_root)

        self.assertEqual(serialized, str(Path("assets") / "default_media" / "Wallpapers_anki"))
        self.assertEqual(manager.resolve_source_folder(serialized), packaged_root.resolve())

    def test_normalize_media_selection_clears_invalid_folder_selection_instead_of_autopicking(self) -> None:
        source_dir = self.root / "wallpapers"
        self._write_media(source_dir / "loop.gif")
        manager = ConfigManager(addon_root=self.root / "folder-root")

        manager.data["media"]["source_folder"] = str(source_dir)
        manager.data["media"]["selected_file"] = "missing.gif"
        manager._normalize_media_selection()

        self.assertEqual(manager.data["media"]["selected_file"], "")


if __name__ == "__main__":
    unittest.main()
