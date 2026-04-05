from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtGui import QImage

from src.config.config_manager import ConfigManager


class ConfigManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def _write_png(self, path: Path, size_bytes: int | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if size_bytes is None:
            image = QImage(1, 1, QImage.Format.Format_ARGB32)
            image.fill(0xFFFFFFFF)
            image.save(str(path))
            return
        path.write_bytes(b"\x00" * size_bytes)

    def test_reload_normalizes_invalid_config_and_drops_legacy_source_url_on_save(self) -> None:
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
        self.assertEqual(manager.data["media"]["trim_start"], 0.0)
        self.assertEqual(manager.data["media"]["trim_end"], 1.25)
        self.assertEqual(manager.data["media"]["opacity"], 1.0)
        self.assertEqual(manager.data["media"]["blur"], 0)
        self.assertEqual(manager.data["media"]["zoom"], 1.0)
        self.assertFalse(manager.data["media"]["muted"])
        self.assertFalse(manager.data["media"]["bounce"])
        self.assertEqual(manager.data["media"]["playback_rate"], 3.0)

        manager.save()
        persisted = json.loads((user_files / "config.json").read_text(encoding="utf-8"))
        self.assertNotIn("source_url", persisted["media"])

    def test_commit_media_prefers_link_then_copy_fallback(self) -> None:
        source = self.root / "source.png"
        self._write_png(source)

        linked_manager = ConfigManager(addon_root=self.root / "link-root")
        with mock.patch("src.config.config_manager.os.link") as mocked_link:
            mocked_link.side_effect = lambda src, dst: shutil.copy2(src, dst)
            committed_name = linked_manager.commit_media_from_path(source)
        self.assertTrue(mocked_link.called)
        self.assertTrue(linked_manager.media_path(committed_name).is_file())

        copied_manager = ConfigManager(addon_root=self.root / "copy-root")
        with (
            mock.patch("src.config.config_manager.os.link", side_effect=OSError("cross-device")),
            mock.patch(
                "src.config.config_manager.shutil.copy2",
                wraps=shutil.copy2,
            ) as mocked_copy,
        ):
            copied_name = copied_manager.commit_media_from_path(source)
        self.assertTrue(mocked_copy.called)
        self.assertTrue(copied_manager.media_path(copied_name).is_file())

    def test_commit_media_reuses_existing_match(self) -> None:
        source = self.root / "reuse.png"
        self._write_png(source)

        manager = ConfigManager(addon_root=self.root / "reuse-root")
        first_name = manager.commit_media_from_path(source)
        second_name = manager.commit_media_from_path(source)

        self.assertEqual(first_name, second_name)
        self.assertEqual(manager.list_media_files(), [first_name])

    def test_list_source_folder_files_recurses_and_returns_relative_paths(self) -> None:
        source_dir = self.root / "wallpapers"
        self._write_png(source_dir / "root.png")
        self._write_png(source_dir / "anime" / "loop.png")
        self._write_png(source_dir / "nature" / "forest" / "loop.png")

        manager = ConfigManager(addon_root=self.root / "scan-root")

        self.assertEqual(
            manager.list_source_folder_files(str(source_dir)),
            [
                str(Path("anime") / "loop.png"),
                str(Path("nature") / "forest" / "loop.png"),
                "root.png",
            ],
        )

    def test_resolve_source_folder_media_path_rejects_escape_paths(self) -> None:
        source_dir = self.root / "wallpapers"
        self._write_png(source_dir / "safe.png")
        outside_file = self.root / "outside.png"
        self._write_png(outside_file)

        manager = ConfigManager(addon_root=self.root / "resolve-root")

        self.assertEqual(
            manager.resolve_source_folder_media_path(str(source_dir), "safe.png"),
            (source_dir / "safe.png").resolve(),
        )
        self.assertIsNone(
            manager.resolve_source_folder_media_path(str(source_dir), str(Path("..") / "outside.png"))
        )

    def test_first_reload_defaults_to_packaged_wallpaper_folder(self) -> None:
        default_source = self.root / "user_files" / "media" / "Wallpapers_anki" / "Smoke"
        self._write_png(default_source / "default.png")

        manager = ConfigManager(addon_root=self.root)

        self.assertEqual(
            manager.data["media"]["source_folder"], str(Path("user_files") / "media" / "Wallpapers_anki")
        )
        self.assertEqual(manager.data["media"]["selected_file"], str(Path("Smoke") / "default.png"))

    def test_reset_to_defaults_restores_packaged_folder_and_clears_imported_media(self) -> None:
        packaged_source = self.root / "user_files" / "media" / "Wallpapers_anki" / "Smoke"
        self._write_png(packaged_source / "default.png")
        imported_source = self.root / "custom.png"
        self._write_png(imported_source)

        manager = ConfigManager(addon_root=self.root)
        managed_name = manager.commit_media_from_path(imported_source)
        manager.data["tutorial_seen"] = True
        manager.data["media"]["source_folder"] = ""
        manager.data["media"]["selected_file"] = managed_name
        manager.save()

        failed_removals = manager.reset_to_defaults()

        self.assertEqual(failed_removals, [])
        self.assertTrue(manager.data["tutorial_seen"])
        self.assertEqual(
            manager.data["media"]["source_folder"], str(Path("user_files") / "media" / "Wallpapers_anki")
        )
        self.assertEqual(manager.data["media"]["selected_file"], str(Path("Smoke") / "default.png"))
        self.assertFalse(manager.media_path(managed_name).exists())

    def test_reset_to_defaults_reports_locked_managed_files_without_crashing(self) -> None:
        packaged_source = self.root / "user_files" / "media" / "Wallpapers_anki" / "Smoke"
        self._write_png(packaged_source / "default.png")
        imported_source = self.root / "custom.png"
        self._write_png(imported_source)

        manager = ConfigManager(addon_root=self.root)
        managed_name = manager.commit_media_from_path(imported_source)

        with mock.patch("pathlib.Path.unlink", side_effect=PermissionError("locked")):
            failed_removals = manager.reset_to_defaults()

        self.assertEqual(failed_removals, [managed_name])
        self.assertTrue(manager.data["tutorial_seen"])
        self.assertEqual(manager.data["media"]["selected_file"], str(Path("Smoke") / "default.png"))

    def test_serialize_and_resolve_packaged_source_folder_as_addon_relative_path(self) -> None:
        packaged_root = self.root / "user_files" / "media" / "Wallpapers_anki"
        packaged_root.mkdir(parents=True, exist_ok=True)
        manager = ConfigManager(addon_root=self.root)

        serialized = manager.serialize_source_folder(packaged_root)

        self.assertEqual(serialized, str(Path("user_files") / "media" / "Wallpapers_anki"))
        self.assertEqual(manager.resolve_source_folder(serialized), packaged_root.resolve())


if __name__ == "__main__":
    unittest.main()
