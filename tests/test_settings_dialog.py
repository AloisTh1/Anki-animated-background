from __future__ import annotations

import importlib
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from src.config.config_manager import ConfigManager
from tests.fake_aqt import install_fake_aqt

install_fake_aqt()
settings_dialog_module = importlib.import_module("src.view.settings_dialog")
SettingsDialog = settings_dialog_module.SettingsDialog


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.config = ConfigManager(addon_root=self.root)

        self.info_patcher = mock.patch.object(
            settings_dialog_module, "showInfo", lambda *args, **kwargs: None
        )
        self.warning_patcher = mock.patch.object(
            settings_dialog_module, "showWarning", lambda *args, **kwargs: None
        )
        self.info_patcher.start()
        self.warning_patcher.start()
        self.addCleanup(self.info_patcher.stop)
        self.addCleanup(self.warning_patcher.stop)

    def _write_png(self, path: Path, size_bytes: int | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if size_bytes is None:
            image = QImage(1, 1, QImage.Format.Format_ARGB32)
            image.fill(0xFFFFFFFF)
            image.save(str(path))
            return
        path.write_bytes(b"\x00" * size_bytes)

    def _stage_managed_media(self, name: str = "managed.png") -> str:
        source = self.root / name
        self._write_png(source)
        managed_name = self.config.commit_media_from_path(source)
        self.config.data["media"]["selected_file"] = managed_name
        return managed_name

    def test_external_folder_live_updates_do_not_write_until_accept(self) -> None:
        managed_name = self._stage_managed_media()
        original_data = deepcopy(self.config.data)
        external_file = self.root / "external" / "sample.png"
        self._write_png(external_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)
        initial_files = self.config.list_media_files()

        dialog.folder_input.setText(str(external_file.parent))
        dialog._refresh_media_selector(external_file.name)
        self.assertTrue(dialog._confirm_current_media_selection_or_revert())
        dialog._apply_live_update()
        dialog.opacity_slider.setValue(dialog.opacity_slider.value() + 5)

        self.assertEqual(self.config.list_media_files(), initial_files)
        self.assertEqual(dialog.media_selector.currentData(), external_file.name)
        self.assertIsNotNone(self.config.runtime_media_override())

        dialog.reject()

        self.assertEqual(self.config.data, original_data)
        self.assertIsNone(self.config.runtime_media_override())
        self.assertEqual(self.config.list_media_files(), initial_files)
        self.assertEqual(self.config.data["media"]["selected_file"], managed_name)

    def test_accept_commits_staged_external_media_once(self) -> None:
        self._stage_managed_media()
        external_file = self.root / "external" / "commit-me.png"
        self._write_png(external_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)
        initial_count = len(self.config.list_media_files())

        dialog.folder_input.setText(str(external_file.parent))
        dialog._refresh_media_selector(external_file.name)
        self.assertTrue(dialog._confirm_current_media_selection_or_revert())
        dialog.accept()

        self.assertIsNone(self.config.runtime_media_override())
        self.assertEqual(len(self.config.list_media_files()), initial_count + 1)
        self.assertEqual(self.config.data["media"]["source_folder"], "")
        self.assertTrue(self.config.media_path(self.config.data["media"]["selected_file"]).is_file())

    def test_recursive_external_folder_lists_relative_paths_and_previews_nested_file(self) -> None:
        self._stage_managed_media()
        source_dir = self.root / "external"
        nested_file = source_dir / "anime" / "scene1" / "clip.png"
        self._write_png(nested_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        relative_name = str(Path("anime") / "scene1" / "clip.png")
        dialog.folder_input.setText(str(source_dir))
        dialog._refresh_media_selector(relative_name)

        self.assertEqual(dialog.media_selector.currentData(), relative_name)
        self.assertTrue(dialog._confirm_current_media_selection_or_revert())
        self.assertEqual(dialog._current_media_preview_path(), nested_file.resolve())

    def test_duplicate_nested_filenames_remain_distinct(self) -> None:
        self._stage_managed_media()
        source_dir = self.root / "external"
        first_file = source_dir / "anime" / "loop.png"
        second_file = source_dir / "nature" / "loop.png"
        self._write_png(first_file)
        self._write_png(second_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog.folder_input.setText(str(source_dir))
        dialog._refresh_media_selector(str(Path("nature") / "loop.png"))

        selector_values = [
            dialog.media_selector.itemData(index) for index in range(dialog.media_selector.count())
        ]
        self.assertIn(str(Path("anime") / "loop.png"), selector_values)
        self.assertIn(str(Path("nature") / "loop.png"), selector_values)
        self.assertEqual(dialog.media_selector.currentData(), str(Path("nature") / "loop.png"))

    def test_media_selector_always_offers_none_option(self) -> None:
        self._stage_managed_media()
        source_dir = self.root / "external"
        nested_file = source_dir / "anime" / "scene1" / "clip.png"
        self._write_png(nested_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog.folder_input.setText(str(source_dir))
        dialog._refresh_media_selector(str(Path("anime") / "scene1" / "clip.png"))

        self.assertEqual(dialog.media_selector.itemText(0), "None")
        self.assertEqual(dialog.media_selector.itemData(0), "")

    def test_build_live_config_allows_none_selection_for_folder_source(self) -> None:
        source_dir = self.root / "external"
        self._write_png(source_dir / "sample.png")

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog.folder_input.setText(str(source_dir))
        dialog._refresh_media_selector()
        dialog.media_selector.setCurrentIndex(0)

        staged = dialog._build_live_config(show_errors=True)

        self.assertIsNotNone(staged)
        updated, resolved_media_path = staged
        self.assertEqual(updated["media"]["source_folder"], str(Path("external")))
        self.assertEqual(updated["media"]["selected_file"], "")
        self.assertIsNone(resolved_media_path)

    def test_accept_commits_nested_external_media_and_reopens_with_same_nested_selection(self) -> None:
        self._stage_managed_media()
        source_dir = self.root / "external"
        nested_file = source_dir / "anime" / "scene1" / "commit-me.png"
        self._write_png(nested_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        relative_name = str(Path("anime") / "scene1" / "commit-me.png")
        dialog.folder_input.setText(str(source_dir))
        dialog._refresh_media_selector(relative_name)
        self.assertTrue(dialog._confirm_current_media_selection_or_revert())
        dialog.accept()

        reopened = SettingsDialog(self.config)
        self.addCleanup(reopened.close)

        self.assertEqual(self.config.data["media"]["source_folder"], "")
        self.assertEqual(reopened.media_selector.currentData(), self.config.data["media"]["selected_file"])
        self.assertEqual(
            reopened._current_media_preview_path(),
            self.config.media_path(self.config.data["media"]["selected_file"]).resolve(),
        )

    def test_large_file_rejection_reverts_folder_and_selection(self) -> None:
        managed_name = self._stage_managed_media()
        large_file = self.root / "external" / "large.png"
        self._write_png(large_file, size_bytes=16 * 1024 * 1024)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        with mock.patch.object(SettingsDialog, "_ask_confirmation", return_value=False):
            dialog.folder_input.setText(str(large_file.parent))
            dialog._refresh_media_selector(large_file.name)
            self.assertFalse(dialog._confirm_current_media_selection_or_revert())

        self.assertEqual(dialog.folder_input.text(), "")
        self.assertEqual(dialog.media_selector.currentData(), managed_name)

    def test_initial_large_preview_is_gated_without_prompting_on_dialog_open(self) -> None:
        large_source = self.root / "huge.png"
        self._write_png(large_source, size_bytes=16 * 1024 * 1024)
        managed_name = self.config.commit_media_from_path(large_source)
        self.config.data["media"]["selected_file"] = managed_name

        with mock.patch.object(SettingsDialog, "_ask_confirmation") as mocked_confirmation:
            dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        mocked_confirmation.assert_not_called()
        self.assertIn("Preview paused", dialog.preview_status_label.text())

    def test_reset_addon_restores_first_run_defaults(self) -> None:
        packaged_source = self.root / "user_files" / "media" / "Wallpapers_anki" / "Smoke"
        self._write_png(packaged_source / "default.png")
        managed_name = self._stage_managed_media("custom.png")
        self.config.data["media"]["source_folder"] = ""
        self.config.data["media"]["selected_file"] = managed_name
        self.config.save()

        info_messages: list[str] = []
        with (
            mock.patch.object(SettingsDialog, "_ask_confirmation", return_value=True),
            mock.patch.object(
                settings_dialog_module,
                "showInfo",
                side_effect=lambda message, *args, **kwargs: info_messages.append(message),
            ),
        ):
            dialog = SettingsDialog(self.config)
            self.addCleanup(dialog.close)
            dialog._reset_addon()

        self.assertEqual(dialog.folder_input.text(), str(Path("user_files") / "media" / "Wallpapers_anki"))
        self.assertEqual(dialog.media_selector.currentData(), str(Path("Smoke") / "default.png"))
        self.assertIn("reset to its default first-run state", info_messages[0])

    def test_reset_addon_warns_when_managed_file_cannot_be_removed(self) -> None:
        packaged_source = self.root / "user_files" / "media" / "Wallpapers_anki" / "Smoke"
        self._write_png(packaged_source / "default.png")
        managed_name = self._stage_managed_media("locked.png")

        warning_messages: list[str] = []
        with (
            mock.patch.object(SettingsDialog, "_ask_confirmation", return_value=True),
            mock.patch.object(
                self.config,
                "remove_managed_media_files",
                return_value=[managed_name],
            ),
            mock.patch.object(
                settings_dialog_module,
                "showWarning",
                side_effect=lambda message, *args, **kwargs: warning_messages.append(message),
            ),
        ):
            dialog = SettingsDialog(self.config)
            self.addCleanup(dialog.close)
            dialog._reset_addon()

        self.assertIn(managed_name, warning_messages[0])

    def test_zoom_slider_resizes_preview_image_like_live_background(self) -> None:
        managed_name = self._stage_managed_media()

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)
        dialog.resize(900, 700)
        dialog._refresh_preview()

        initial_bounds = dialog.preview_image_item.boundingRect().size()
        initial_scale = dialog.preview_image_item.scale()
        self.assertEqual(dialog.media_selector.currentData(), managed_name)

        dialog.zoom_slider.setValue(160)

        self.assertGreater(dialog.preview_image_item.scale(), initial_scale)
        self.assertEqual(dialog.preview_image_item.boundingRect().size(), initial_bounds)

    def test_changing_media_resets_trim_to_defaults(self) -> None:
        first_file = self.root / "external" / "first.png"
        second_file = self.root / "external" / "second.png"
        self._write_png(first_file)
        self._write_png(second_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)
        dialog.folder_input.setText(str(first_file.parent))
        dialog._refresh_media_selector(first_file.name)
        self.assertTrue(dialog._confirm_current_media_selection_or_revert())
        dialog._trim_start_seconds = 1.25
        dialog._trim_end_seconds = 4.5
        dialog._update_trim_slider_window()

        dialog._refresh_media_selector(second_file.name)
        dialog._on_media_selection_changed(dialog.media_selector.currentIndex())

        self.assertEqual(dialog.media_selector.currentData(), second_file.name)
        self.assertEqual(dialog._trim_start_seconds, 0.0)
        self.assertEqual(dialog._trim_end_seconds, 0.0)
        self.assertEqual(dialog.trim_start_slider.value(), 0)
        self.assertEqual(dialog.trim_end_slider.value(), dialog.trim_end_slider.maximum())

    def test_accept_keeps_packaged_source_selection_without_copying_to_managed_root(self) -> None:
        packaged_root = (self.root / "user_files" / "media" / "Wallpapers_anki").resolve()
        nested_file = packaged_root / "Smoke" / "default.png"
        self._write_png(nested_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)
        dialog.folder_input.setText(str(packaged_root))
        dialog._refresh_media_selector(str(Path("Smoke") / "default.png"))
        self.assertTrue(dialog._confirm_current_media_selection_or_revert())
        dialog.accept()

        self.assertEqual(
            self.config.data["media"]["source_folder"], str(Path("user_files") / "media" / "Wallpapers_anki")
        )
        self.assertEqual(self.config.data["media"]["selected_file"], str(Path("Smoke") / "default.png"))
        self.assertFalse(self.config.media_path("default.png").exists())

    def test_bounce_checkbox_is_saved_in_live_config(self) -> None:
        self._stage_managed_media()
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog.bounce_checkbox.setChecked(True)
        staged = dialog._build_live_config(show_errors=True)

        self.assertIsNotNone(staged)
        updated, _resolved = staged
        self.assertTrue(updated["media"]["bounce"])

    def test_trim_change_with_bounce_resets_preview_direction_forward(self) -> None:
        self._stage_managed_media()
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog.bounce_checkbox.setChecked(True)
        dialog._preview_source = self.config.media_path(self.config.data["media"]["selected_file"])
        dialog._preview_duration_seconds = 8.0
        dialog._preview_direction = -1
        dialog._trim_start_seconds = 2.0
        dialog._trim_end_seconds = 6.0

        with (
            mock.patch.object(dialog.preview_player, "setPlaybackRate") as mocked_rate,
            mock.patch.object(dialog.preview_player, "setPosition") as mocked_position,
        ):
            dialog._on_preview_trim_changed()

        self.assertEqual(dialog._preview_direction, 1)
        mocked_rate.assert_called()
        mocked_position.assert_called_with(2000)

    def test_trim_end_full_media_maps_to_slider_max(self) -> None:
        self._stage_managed_media()
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog._preview_duration_seconds = 8.0
        dialog._trim_end_seconds = 0.0
        dialog._update_trim_slider_window()

        self.assertEqual(dialog.trim_end_slider.value(), dialog.trim_end_slider.maximum())
        self.assertIn("Full media", dialog.trim_range_end_label.text())

    def test_trim_end_slider_minimum_maps_to_small_positive_value(self) -> None:
        self._stage_managed_media()
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog._preview_duration_seconds = 8.0
        dialog._update_trim_slider_window()
        dialog.trim_end_slider.setValue(0)

        self.assertEqual(dialog._trim_end_seconds, 0.01)
        self.assertEqual(dialog.trim_range_end_label.text(), "End: 0.01s")

    def test_choose_folder_opens_current_folder_when_available(self) -> None:
        source_dir = self.root / "external"
        self._write_png(source_dir / "sample.png")
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)
        dialog.folder_input.setText(str(source_dir))

        with mock.patch.object(
            settings_dialog_module.QFileDialog,
            "getExistingDirectory",
            return_value="",
        ) as mocked_picker:
            dialog._choose_source_folder()

        mocked_picker.assert_called_once_with(dialog, "Choose Background Media Folder", str(source_dir))


if __name__ == "__main__":
    unittest.main()
