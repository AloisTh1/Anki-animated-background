from __future__ import annotations

import importlib
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from tests.fake_aqt import install_fake_aqt

install_fake_aqt()

aqt_qt = importlib.import_module("aqt.qt")
QApplication = aqt_qt.QApplication
QRect = aqt_qt.QRect
QScrollArea = aqt_qt.QScrollArea

config_manager_module = importlib.import_module("src.config.config_manager")
ConfigManager = config_manager_module.ConfigManager

settings_dialog_module = importlib.import_module("src.view.settings_dialog")
SettingsDialog = settings_dialog_module.SettingsDialog

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

    def _write_media(self, path: Path, *, payload: bytes = MINIMAL_GIF) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def _stage_managed_media(self, name: str = "managed.gif") -> str:
        source = self.root / name
        self._write_media(source)
        managed_name = self.config.commit_media_from_path(source)
        self.config.data["media"]["selected_file"] = managed_name
        return managed_name

    def test_media_selector_always_offers_none_option(self) -> None:
        source_dir = self.root / "external"
        self._write_media(source_dir / "anime" / "scene1" / "clip.gif")

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog.folder_input.setText(str(source_dir))
        dialog._refresh_media_selector(str(Path("anime") / "scene1" / "clip.gif"))

        self.assertEqual(dialog.media_selector.itemText(0), "None")
        self.assertEqual(dialog.media_selector.itemData(0), "")

    def test_choose_source_folder_does_not_auto_select_media(self) -> None:
        source_dir = self.root / "external"
        self._write_media(source_dir / "sample.gif")

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        with mock.patch.object(
            settings_dialog_module.QFileDialog,
            "getExistingDirectory",
            return_value=str(source_dir),
        ):
            dialog._choose_source_folder()

        self.assertEqual(dialog.folder_input.text(), str(source_dir))
        self.assertEqual(dialog.media_selector.currentData(), "")

    def test_build_live_config_allows_none_selection_for_folder_source(self) -> None:
        source_dir = self.root / "external"
        self._write_media(source_dir / "sample.gif")

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

    def test_external_folder_live_updates_set_runtime_override_without_persisting_selection(self) -> None:
        managed_name = self._stage_managed_media()
        original_data = deepcopy(self.config.data)
        external_file = self.root / "external" / "sample.gif"
        self._write_media(external_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog.folder_input.setText(str(external_file.parent))
        dialog._refresh_media_selector(external_file.name)
        dialog._apply_live_update()

        self.assertEqual(dialog.media_selector.currentData(), external_file.name)
        self.assertEqual(self.config.data["media"]["source_folder"], str(Path("external")))
        self.assertEqual(self.config.data["media"]["selected_file"], external_file.name)
        self.assertEqual(self.config.runtime_media_override(), external_file.resolve())

        dialog.reject()

        self.assertEqual(self.config.data, original_data)
        self.assertIsNone(self.config.runtime_media_override())
        self.assertEqual(self.config.data["media"]["selected_file"], managed_name)

    def test_accept_persists_external_folder_selection_without_copying_to_managed_media(self) -> None:
        source_dir = self.root / "external"
        nested_file = source_dir / "anime" / "scene1" / "clip.gif"
        self._write_media(nested_file)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        relative_name = str(Path("anime") / "scene1" / "clip.gif")
        dialog.folder_input.setText(str(source_dir))
        dialog._refresh_media_selector(relative_name)
        dialog.accept()

        self.assertIsNone(self.config.runtime_media_override())
        self.assertEqual(self.config.data["media"]["source_folder"], str(Path("external")))
        self.assertEqual(self.config.data["media"]["selected_file"], relative_name)
        self.assertEqual(self.config.resolve_media_path(), nested_file.resolve())
        self.assertEqual(self.config.list_media_files(), [])

    def test_choose_folder_opens_resolved_current_folder_when_available(self) -> None:
        source_dir = self.root / "user_files" / "media" / "Wallpapers_anki"
        self._write_media(source_dir / "sample.gif")
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)
        dialog.folder_input.setText(str(Path("user_files") / "media" / "Wallpapers_anki"))

        with mock.patch.object(
            settings_dialog_module.QFileDialog,
            "getExistingDirectory",
            return_value="",
        ) as mocked_picker:
            dialog._choose_source_folder()

        mocked_picker.assert_called_once_with(
            dialog, "Choose Background Media Folder", str(source_dir.resolve())
        )

    def test_large_file_rejection_reverts_folder_and_selection(self) -> None:
        managed_name = self._stage_managed_media()
        large_file = self.root / "external" / "large.gif"
        self._write_media(large_file, payload=b"\x00" * (21 * 1024 * 1024))

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        with mock.patch.object(SettingsDialog, "_ask_confirmation", return_value=False):
            dialog.folder_input.setText(str(large_file.parent))
            dialog._refresh_media_selector(large_file.name)
            self.assertFalse(dialog._confirm_current_media_selection_or_revert())

        self.assertEqual(dialog.folder_input.text(), "")
        self.assertEqual(dialog.media_selector.currentData(), managed_name)

    def test_initial_large_preview_is_gated_without_prompting_on_dialog_open(self) -> None:
        large_source = self.root / "huge.gif"
        self._write_media(large_source, payload=b"\x00" * (21 * 1024 * 1024))
        managed_name = self.config.commit_media_from_path(large_source)
        self.config.data["media"]["selected_file"] = managed_name

        with mock.patch.object(SettingsDialog, "_ask_confirmation") as mocked_confirmation:
            dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        mocked_confirmation.assert_not_called()
        self.assertIn("Preview paused", dialog.preview_status_label.text())

    def test_reset_addon_is_staged_until_save_and_cancel_restores_original_data(self) -> None:
        packaged_source = self.root / "user_files" / "media" / "Wallpapers_anki" / "Smoke"
        self._write_media(packaged_source / "default.gif")
        managed_name = self._stage_managed_media("custom.gif")
        self.config.data["media"]["source_folder"] = ""
        self.config.data["media"]["selected_file"] = managed_name
        self.config.save()
        original_data = deepcopy(self.config.data)

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        with mock.patch.object(SettingsDialog, "_ask_confirmation", return_value=True):
            dialog._reset_addon()

        self.assertTrue(dialog._reset_staged)
        self.assertEqual(dialog.folder_input.text(), str(Path("user_files") / "media" / "Wallpapers_anki"))
        self.assertEqual(dialog.media_selector.currentData(), "")

        dialog.reject()

        self.assertEqual(self.config.data, original_data)
        self.assertIsNone(self.config.runtime_media_override())

    def test_reset_addon_removes_managed_media_on_save(self) -> None:
        packaged_source = self.root / "user_files" / "media" / "Wallpapers_anki" / "Smoke"
        self._write_media(packaged_source / "default.gif")
        managed_name = self._stage_managed_media("custom.gif")
        self.config.save()

        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        with mock.patch.object(SettingsDialog, "_ask_confirmation", return_value=True):
            dialog._reset_addon()
        dialog.accept()

        self.assertFalse(self.config.media_path(managed_name).exists())
        self.assertEqual(
            self.config.data["media"]["source_folder"], str(Path("user_files") / "media" / "Wallpapers_anki")
        )
        self.assertEqual(self.config.data["media"]["selected_file"], "")

    def test_dialog_wraps_main_content_in_scroll_area(self) -> None:
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        scroll_area = dialog.findChild(QScrollArea, "settingsScrollArea")

        self.assertIsNotNone(scroll_area)
        self.assertTrue(scroll_area.widgetResizable())

    def test_dialog_initial_size_respects_available_screen_geometry(self) -> None:
        with mock.patch.object(
            SettingsDialog,
            "_available_screen_geometry",
            return_value=QRect(0, 0, 900, 640),
        ):
            dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        self.assertLessEqual(dialog.width(), 828)
        self.assertLessEqual(dialog.height(), 568)

    def test_dialog_relaxes_large_widget_minimums_for_smaller_screens(self) -> None:
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        self.assertLessEqual(dialog.header_logo.minimumWidth(), 260)
        self.assertLessEqual(dialog.header_logo.minimumHeight(), 108)
        self.assertLessEqual(dialog.preview_view.minimumWidth(), 280)
        self.assertLessEqual(dialog.preview_status_label.minimumWidth(), 220)

    def test_preview_maintains_practical_minimum_height_after_shrink(self) -> None:
        dialog = SettingsDialog(self.config)
        self.addCleanup(dialog.close)

        dialog.resize(760, 520)
        self.app.processEvents()

        self.assertGreaterEqual(dialog.preview_view.minimumHeight(), 158)


if __name__ == "__main__":
    unittest.main()
