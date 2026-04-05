from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import os
from pathlib import Path

from aqt import qconnect
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMovie,
    QPushButton,
    QSizePolicy,
    QSlider,
    Qt,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showInfo, showWarning
from PyQt6.QtCore import QPointF, QSizeF, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt6.QtWidgets import (
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QMenu,
    QMessageBox,
)

from ..config.config_manager import DEFAULT_CONFIG, ConfigManager
from .branding import create_brand_icon, create_brand_pixmap

VIDEO_EXTENSIONS = {".mp4", ".webm"}
LARGE_VIDEO_WARNING_BYTES = 50 * 1024 * 1024
LARGE_GIF_WARNING_BYTES = 20 * 1024 * 1024
PREVIEW_MAX_WIDTH = 480
PREVIEW_MAX_HEIGHT = 270
TRIM_SLIDER_SCALE = 100
PALETTE_TEXT = "#f7f9fb"
PALETTE_CYAN = "#11d7d6"
PALETTE_GREEN = "#34d58c"
PALETTE_BLUE = "#2d9cff"
PALETTE_PURPLE = "#7754ff"
PALETTE_PURPLE_SOFT = "#9d86ff"
PALETTE_PURPLE_DEEP = "#4d2bd1"
PALETTE_AMBER = "#ffb347"
SUPPORT_LINKS = [
    ("Website", "https://aloisthibert.dev/en/anki"),
    ("Patreon", "https://www.patreon.com/home"),
    ("Buy Me a Coffee", "https://buymeacoffee.com/alois_devlp"),
    ("X / Twitter", "https://x.com/_eRay_y"),
    ("YouTube", "https://www.youtube.com/@Alois_dvlp"),
]

DARK_THEME = {
    "ink": "#111923",
    "panel": "#182430",
    "panel_alt": "#213142",
    "border": "#335166",
    "text": "#f7f9fb",
    "muted": "#c1ccd5",
    "input_bg": "rgba(14, 23, 31, 0.94)",
    "button_hover": "rgba(119, 84, 255, 0.20)",
    "button_pressed": "rgba(119, 84, 255, 0.32)",
    "button_fill": "rgba(119, 84, 255, 0.18)",
    "selection": "rgba(45, 156, 255, 0.38)",
    "slider_groove": "rgba(193, 204, 213, 0.34)",
}

LIGHT_THEME = {
    "ink": "#eef2f7",
    "panel": "#ffffff",
    "panel_alt": "#f6f8fc",
    "border": "#b9c7d5",
    "text": "#1a2230",
    "muted": "#516173",
    "input_bg": "rgba(255, 255, 255, 0.98)",
    "button_hover": "rgba(119, 84, 255, 0.10)",
    "button_pressed": "rgba(119, 84, 255, 0.18)",
    "button_fill": "rgba(119, 84, 255, 0.10)",
    "selection": "rgba(45, 156, 255, 0.20)",
    "slider_groove": "rgba(81, 97, 115, 0.22)",
}


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: ConfigManager,
        on_live_update: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.on_live_update = on_live_update
        self._original_data = deepcopy(config.data)
        self._original_runtime_media_override = config.runtime_media_override()
        self._view_data = self.config.normalize_data(config.data)

        media_config = self._view_data.get("media", {})
        self._preview_source: Path | None = None
        self._preview_kind: str | None = None
        self._preview_duration_seconds = 0.0
        self._preview_movie: QMovie | None = None
        self._approved_large_media_paths: set[str] = set()
        self._trim_start_seconds = float(media_config.get("trim_start", 0.0))
        self._trim_end_seconds = float(media_config.get("trim_end", 0.0))
        self._trim_slider_max_seconds = max(self._trim_start_seconds, self._trim_end_seconds, 1.0)
        self._theme_mode = str(self._view_data.get("theme_mode", "dark"))

        self._last_safe_source_folder = str(media_config.get("source_folder", ""))
        self._last_safe_media_selection = self._initial_selected_name()
        self._applied_media_identity = (self._last_safe_source_folder, self._last_safe_media_selection)
        self._reset_staged = False
        self._cached_folder_path: str = ""
        self._cached_folder_files: list[str] = []

        self.setWindowTitle("Animated Background Settings")
        self.resize(1120, 860)
        self.setObjectName("animatedBackgroundDialog")
        self.setWindowIcon(create_brand_icon(self._theme_mode))

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(18)
        root_layout.addWidget(self._build_header_row())

        content = QWidget(self)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)

        controls_column = QWidget(content)
        controls_layout = QVBoxLayout(controls_column)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(16)
        controls_layout.addWidget(self._build_target_group())
        controls_layout.addWidget(self._build_media_group())
        controls_layout.addWidget(self._build_display_group())
        controls_layout.addWidget(self._build_trim_group())
        controls_layout.addWidget(self._build_footer_controls())
        controls_layout.addStretch(1)

        preview_column = self._build_preview_group()

        content_layout.addWidget(controls_column, 3)
        content_layout.addWidget(preview_column, 2)
        root_layout.addWidget(content)

        actions_row = QWidget(self)
        actions_layout = QHBoxLayout(actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(14)
        actions_layout.addStretch(1)
        self.reset_addon_button = QPushButton("Reset", actions_row)
        self.save_settings_button = QPushButton("Save Settings", actions_row)
        self.save_settings_button.setObjectName("primaryActionButton")
        self.save_settings_button.setMinimumWidth(220)
        actions_layout.addWidget(self.reset_addon_button)
        actions_layout.addWidget(self.save_settings_button)
        qconnect(self.reset_addon_button.clicked, self._reset_addon)
        qconnect(self.save_settings_button.clicked, self.accept)
        root_layout.addWidget(actions_row)

        self.folder_input.setText(self._last_safe_source_folder)
        self._refresh_media_selector(self._last_safe_media_selection)
        self._connect_live_update_signals()
        self._apply_tooltips()
        self._apply_site_palette()
        self._refresh_preview_with_guard(allow_prompt=False)

    def closeEvent(self, event) -> None:
        self._clear_preview("Select media to preview")
        super().closeEvent(event)

    def accept(self) -> None:
        if not self._confirm_current_media_selection_or_revert():
            return

        staged = self._build_live_config(show_errors=True)
        if staged is None:
            return

        updated, _resolved_media_path = staged
        self.config.clear_runtime_media_override()
        self.config.data = self.config.normalize_data(updated)

        if self._reset_staged:
            failed = self.config.remove_managed_media_files()
            if failed:
                showWarning(
                    "Settings were reset, but some imported media files could not be removed:\n\n"
                    + "\n".join(failed)
                )

        super().accept()

    def reject(self) -> None:
        self.config.data = deepcopy(self._original_data)
        self.config.set_runtime_media_override(self._original_runtime_media_override)
        if self.on_live_update:
            self.on_live_update()
        super().reject()

    def _build_header_row(self) -> QWidget:
        header = QWidget(self)
        header.setObjectName("topHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(6, 4, 6, 10)
        layout.setSpacing(24)

        self.header_logo = QLabel(header)
        self.header_logo.setObjectName("dialogLogo")
        self.header_logo.setMinimumSize(420, 150)
        self.header_logo.setPixmap(create_brand_pixmap(size=360, theme_mode=self._theme_mode))
        self.header_logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        controls_column = QWidget(header)
        controls_layout = QVBoxLayout(controls_column)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(14)

        self.enabled_checkbox = QCheckBox("")
        self.enabled_checkbox.setObjectName("enabledSwitch")
        self.enabled_checkbox.setChecked(bool(self._view_data.get("enabled", True)))
        self.theme_selector = QComboBox(header)
        self.theme_selector.addItem("Dark", "dark")
        self.theme_selector.addItem("Light", "light")
        current_theme_index = max(0, self.theme_selector.findData(self._theme_mode))
        self.theme_selector.setCurrentIndex(current_theme_index)
        self.support_button = QPushButton("💖 Support", header)
        self.support_button.setObjectName("supportButton")
        self.support_menu = QMenu(self.support_button)
        support_labels = {
            "Website": "🌐 Website",
            "Patreon": "💖 Patreon",
            "Buy Me a Coffee": "☕ Buy Me a Coffee",
            "X / Twitter": "𝕏 X / Twitter",
            "YouTube": "🎬 YouTube",
        }
        for label, url in SUPPORT_LINKS:
            action = QAction(label, self.support_menu)
            action.setText(support_labels.get(label, label))
            qconnect(
                action.triggered, lambda _checked=False, target_url=url: self._open_support_link(target_url)
            )
            self.support_menu.addAction(action)
        self.support_button.setMenu(self.support_menu)

        enabled_row = QWidget(controls_column)
        enabled_layout = QHBoxLayout(enabled_row)
        enabled_layout.setContentsMargins(0, 0, 0, 0)
        enabled_layout.setSpacing(12)
        enabled_label = QLabel("Enable Animated Backgrounds", enabled_row)
        enabled_label.setObjectName("enabledSwitchLabel")
        enabled_layout.addWidget(enabled_label)
        enabled_layout.addStretch(1)
        enabled_layout.addWidget(self.enabled_checkbox, 0, Qt.AlignmentFlag.AlignVCenter)

        controls_layout.addWidget(self.support_button, 0, Qt.AlignmentFlag.AlignRight)
        controls_layout.addWidget(enabled_row)
        controls_layout.addStretch(1)

        layout.addWidget(self.header_logo, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        layout.addWidget(controls_column, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _build_target_group(self) -> QGroupBox:
        group = QGroupBox("Active Screens")
        layout = QHBoxLayout(group)
        targets = self._view_data.get("targets", {})

        self.target_checkboxes = {
            "reviewer": QCheckBox("Reviewer"),
            "deck_browser": QCheckBox("Deck Browser"),
            "main_window": QCheckBox("Overview"),
        }
        self.target_checkboxes["reviewer"].setChecked(bool(targets.get("reviewer", True)))
        self.target_checkboxes["deck_browser"].setChecked(bool(targets.get("deck_browser", True)))
        self.target_checkboxes["main_window"].setChecked(bool(targets.get("main_window", False)))

        for checkbox in self.target_checkboxes.values():
            layout.addWidget(checkbox)
        layout.addStretch(1)

        return group

    def _build_media_group(self) -> QGroupBox:
        media_config = self._view_data.get("media", {})
        group = QGroupBox("Media Source")
        layout = QFormLayout(group)

        self.media_selector = QComboBox(group)
        self.media_hint = QLabel("Supported: GIF, WebM, MP4", group)
        self.media_hint.setObjectName("mediaHintLabel")
        self.folder_input = QLineEdit(str(media_config.get("source_folder", "")), group)
        self.folder_input.setReadOnly(True)
        self.folder_input.setPlaceholderText("Choose a folder of background media")

        buttons = QWidget(group)
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.choose_folder_button = QPushButton("Choose Folder", buttons)
        buttons_layout.addWidget(self.choose_folder_button)
        qconnect(self.choose_folder_button.clicked, self._choose_source_folder)

        layout.addRow("Selected Media", self.media_selector)
        layout.addRow("", self.media_hint)
        layout.addRow("Source Folder", self.folder_input)
        layout.addRow("Actions", buttons)
        return group

    def _build_display_group(self) -> QGroupBox:
        media_config = self._view_data.get("media", {})
        group = QGroupBox("Display")
        layout = QFormLayout(group)

        opacity_widget, self.opacity_slider = self._make_slider(
            media_config.get("opacity", 0.35), 0, 100, 100
        )
        blur_widget, self.blur_slider = self._make_slider(media_config.get("blur", 0), 0, 24, 1)
        zoom_widget, self.zoom_slider = self._make_slider(media_config.get("zoom", 1.0), 100, 160, 100)
        playback_widget, self.playback_rate_slider = self._make_slider(
            media_config.get("playback_rate", 1.0), 25, 300, 100
        )
        self.muted_checkbox = QCheckBox("Mute videos")
        self.muted_checkbox.setChecked(bool(media_config.get("muted", True)))
        layout.addRow(
            "Opacity", self._make_resettable_control(opacity_widget, self.opacity_slider, 100, "opacity")
        )
        layout.addRow("Blur", self._make_resettable_control(blur_widget, self.blur_slider, 1, "blur"))
        layout.addRow("Zoom", self._make_resettable_control(zoom_widget, self.zoom_slider, 100, "zoom"))
        layout.addRow(
            "Playback Rate",
            self._make_resettable_control(playback_widget, self.playback_rate_slider, 100, "playback_rate"),
        )

        qconnect(self.muted_checkbox.toggled, self._on_preview_muted_changed)
        qconnect(self.playback_rate_slider.valueChanged, self._on_preview_playback_rate_changed)
        return group

    def _build_trim_group(self) -> QGroupBox:
        group = QGroupBox("Trim Loop")
        layout = QVBoxLayout(group)
        layout.addWidget(self._build_trim_widget())
        return group

    def _build_footer_controls(self) -> QWidget:
        footer = QWidget(self)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(self.muted_checkbox)
        layout.addStretch(1)

        theme_label = QLabel("Theme", footer)
        theme_label.setObjectName("footerLabel")
        layout.addWidget(theme_label)
        layout.addWidget(self.theme_selector)
        return footer

    def _build_trim_widget(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.trim_range_label = QLabel("Preview duration unknown", widget)
        self.trim_range_start_label = QLabel("Start: 0.00s", widget)
        self.trim_range_end_label = QLabel("End: 0.00s", widget)
        self.trim_range_label.setObjectName("trimMetaLabel")
        self.trim_range_start_label.setObjectName("trimStartLabel")
        self.trim_range_end_label.setObjectName("trimEndLabel")

        self.trim_start_slider = QSlider(Qt.Orientation.Horizontal, widget)
        self.trim_end_slider = QSlider(Qt.Orientation.Horizontal, widget)
        self.trim_start_slider.setObjectName("trimStartSlider")
        self.trim_end_slider.setObjectName("trimEndSlider")

        slider_max = int(round(self._trim_slider_max_seconds * TRIM_SLIDER_SCALE))
        self.trim_start_slider.setRange(0, slider_max)
        self.trim_end_slider.setRange(0, slider_max)
        self.trim_start_slider.setValue(int(round(self._trim_start_seconds * TRIM_SLIDER_SCALE)))
        self.trim_end_slider.setValue(
            self._trim_end_seconds_to_slider_value(self._trim_end_seconds, slider_max)
        )

        qconnect(self.trim_start_slider.valueChanged, self._on_trim_slider_changed)
        qconnect(self.trim_end_slider.valueChanged, self._on_trim_slider_changed)

        layout.addWidget(self.trim_range_label)
        layout.addWidget(self.trim_range_start_label)
        layout.addWidget(self.trim_start_slider)
        layout.addWidget(self.trim_range_end_label)
        layout.addWidget(self.trim_end_slider)

        self._sync_trim_slider_labels()
        return widget

    def _make_resettable_control(
        self,
        control_widget: QWidget,
        slider: QSlider,
        scale: int,
        media_key: str,
    ) -> QWidget:
        wrapper = QWidget(self)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)

        reset_button = QPushButton("Reset", wrapper)
        reset_button.setObjectName("smallResetButton")
        reset_button.setFixedWidth(72)
        qconnect(
            reset_button.clicked,
            lambda _checked=False, *, target_slider=slider, target_scale=scale, key=media_key: (
                self._reset_slider(target_slider, target_scale, key)
            ),
        )

        layout.addWidget(control_widget, 1)
        layout.addWidget(reset_button)
        return wrapper

    def _build_preview_group(self) -> QGroupBox:
        group = QGroupBox("Preview")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        self.preview_view = QGraphicsView(group)
        self.preview_view.setObjectName("previewMediaView")
        self.preview_view.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_view.setMinimumWidth(PREVIEW_MAX_WIDTH)
        self.preview_view.setMinimumHeight(PREVIEW_MAX_HEIGHT)
        self.preview_view.setInteractive(False)
        self.preview_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_view.setStyleSheet("background: rgba(0, 0, 0, 0.18); border: 0;")
        self.preview_scene = QGraphicsScene(self.preview_view)
        self.preview_view.setScene(self.preview_scene)
        self.preview_video_item = QGraphicsVideoItem()
        self.preview_image_item = QGraphicsPixmapItem()
        self.preview_video_item.setVisible(False)
        self.preview_image_item.setVisible(False)
        self.preview_scene.addItem(self.preview_video_item)
        self.preview_scene.addItem(self.preview_image_item)
        layout.addWidget(self.preview_view, 1)

        controls = QWidget(group)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_play_button = QPushButton("Play", controls)
        self.preview_status_label = QLabel("Select media to preview", controls)
        self.preview_status_label.setObjectName("previewStatusLabel")
        self.preview_status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.preview_status_label.setMinimumWidth(340)
        self.preview_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        controls_layout.addWidget(self.preview_play_button)
        controls_layout.addWidget(self.preview_status_label, 1)
        layout.addWidget(controls)

        self.preview_audio_output = QAudioOutput(group)
        self.preview_audio_output.setMuted(True)
        self.preview_player = QMediaPlayer(group)
        self.preview_player.setAudioOutput(self.preview_audio_output)
        self.preview_player.setVideoOutput(self.preview_video_item)

        qconnect(self.preview_play_button.clicked, self._toggle_preview_playback)
        qconnect(self.preview_player.positionChanged, self._on_preview_position_changed)
        qconnect(self.preview_player.durationChanged, self._on_preview_duration_changed)
        qconnect(self.preview_player.mediaStatusChanged, self._on_preview_media_status_changed)
        qconnect(self.preview_video_item.nativeSizeChanged, self._layout_preview_media_item)
        self.preview_play_button.setEnabled(False)
        return group

    def _get_source_folder_files(self, folder: str) -> list[str]:
        if folder == self._cached_folder_path:
            return self._cached_folder_files
        self._cached_folder_path = folder
        self._cached_folder_files = self.config.list_source_folder_files(folder) if folder else []
        return self._cached_folder_files

    def _invalidate_folder_cache(self) -> None:
        self._cached_folder_path = ""
        self._cached_folder_files = []

    def _initial_selected_name(self) -> str:
        media_config = self._view_data.get("media", {})
        source_folder = str(media_config.get("source_folder", ""))
        selected_file = str(media_config.get("selected_file", ""))
        if not source_folder:
            return Path(selected_file).name
        resolved = self._find_matching_source_filename(source_folder, selected_file)
        return resolved or Path(selected_file).name

    def _refresh_media_selector(self, preferred_filename: str | None = None) -> None:
        source_folder = self.folder_input.text().strip()
        files = (
            self._get_source_folder_files(source_folder) if source_folder else self.config.list_media_files()
        )
        current_from_config = self._view_data.get("media", {}).get("selected_file", "")
        target = preferred_filename if preferred_filename is not None else self.media_selector.currentData()
        if not target:
            target = self._resolve_selector_target(source_folder, str(current_from_config))

        self.media_selector.blockSignals(True)
        self.media_selector.clear()
        self.media_selector.addItem("None", "")
        for filename in files:
            self.media_selector.addItem(filename, filename)

        index = self.media_selector.findData(target)
        if index < 0:
            index = 0
        self.media_selector.setCurrentIndex(index)
        self.media_selector.blockSignals(False)

    def _resolve_selector_target(self, source_folder: str, current_from_config: str) -> str:
        if not source_folder:
            return Path(current_from_config).name

        resolved = self._find_matching_source_filename(source_folder, current_from_config)
        return resolved or Path(current_from_config).name

    def _find_matching_source_filename(self, source_folder: str, managed_filename: str) -> str:
        if not managed_filename:
            return ""

        resolved_source_path = self.config.resolve_source_folder_media_path(source_folder, managed_filename)
        if resolved_source_path is not None:
            return managed_filename

        managed_path = self.config.media_path(managed_filename)
        if not managed_path.exists():
            return ""

        for filename in self._get_source_folder_files(source_folder):
            candidate = self.config.resolve_source_folder_media_path(source_folder, filename)
            if candidate is None:
                continue
            try:
                if os.path.samefile(candidate, managed_path):
                    return filename
            except OSError:
                continue

        return ""

    def _choose_source_folder(self) -> None:
        current_folder = self.folder_input.text().strip()
        resolved_current_folder = self.config.resolve_source_folder(current_folder)
        start_folder = str(resolved_current_folder) if resolved_current_folder is not None else ""
        selected_folder = QFileDialog.getExistingDirectory(
            self, "Choose Background Media Folder", start_folder
        )
        if not selected_folder:
            return

        self._invalidate_folder_cache()
        filenames = self._get_source_folder_files(selected_folder)
        if not filenames:
            showWarning("The selected folder does not contain any supported media files.")
            return

        self.folder_input.setText(selected_folder)
        self._refresh_media_selector("")
        if not self._confirm_current_media_selection_or_revert():
            return

        self._apply_live_update()
        showInfo(f"Loaded {len(filenames)} media file(s) from the selected folder.")

    def _current_media_preview_path(self) -> Path | None:
        selected_file = self.media_selector.currentData()
        if not selected_file:
            return None

        source_folder = self.folder_input.text().strip()
        if source_folder:
            return self.config.resolve_source_folder_media_path(source_folder, str(selected_file))

        managed_path = self.config.media_path(str(selected_file))
        return managed_path.resolve() if managed_path.is_file() else None

    def _current_media_identity(self) -> tuple[str, str]:
        return (self.folder_input.text().strip(), str(self.media_selector.currentData() or ""))

    def _refresh_preview_with_guard(self, allow_prompt: bool) -> bool:
        media_path = self._current_media_preview_path()
        if media_path is None or not media_path.is_file():
            self._clear_preview("Select media to preview")
            return True

        warning = self._large_media_warning(media_path)
        media_key = str(media_path)
        if warning and media_key not in self._approved_large_media_paths:
            if not allow_prompt:
                self._clear_preview("Preview paused until the large media file is approved.")
                return False
            confirmed = self._ask_confirmation("Large Background Media", warning)
            if not confirmed:
                self._clear_preview("Preview paused until the large media file is approved.")
                return False
            self._approved_large_media_paths.add(media_key)

        self._refresh_preview()
        return True

    def _refresh_preview(self) -> None:
        media_path = self._current_media_preview_path()
        if media_path is None or not media_path.is_file():
            self._clear_preview("Select media to preview")
            return

        suffix = media_path.suffix.lower()
        self._preview_source = media_path
        if suffix in VIDEO_EXTENSIONS:
            self._show_video_preview(media_path)
            return
        if suffix == ".gif":
            self._show_gif_preview(media_path)
            return
        self._clear_preview("Select media to preview")

    def _clear_preview(self, message: str) -> None:
        self._preview_source = None
        self._preview_kind = None
        self._preview_duration_seconds = 0.0
        if self._preview_movie is not None:
            self._preview_movie.stop()
            self._preview_movie = None
        self.preview_image_item.setPixmap(QPixmap())
        self.preview_image_item.setVisible(False)
        self.preview_video_item.setVisible(False)
        self.preview_player.stop()
        self.preview_player.setSource(QUrl())
        self._apply_preview_media_style()
        self._layout_preview_media_item()
        self.preview_play_button.setEnabled(False)
        self.preview_play_button.setText("Play")
        self.preview_status_label.setText(message)

    def _toggle_preview_playback(self) -> None:
        if self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_player.pause()
            self.preview_play_button.setText("Play")
        else:
            self.preview_player.play()
            self.preview_play_button.setText("Pause")

    def _on_preview_duration_changed(self, duration_ms: int) -> None:
        self._preview_duration_seconds = max(0.0, duration_ms / 1000)
        self._update_trim_slider_window()
        self._apply_preview_trim()
        self._update_preview_status(self.preview_player.position())

    def _on_preview_position_changed(self, position_ms: int) -> None:
        trim_start = self._trim_start_seconds
        trim_end = self._effective_preview_trim_end()
        current_seconds = position_ms / 1000

        if trim_end > trim_start and current_seconds >= trim_end:
            self.preview_player.setPosition(int(trim_start * 1000))
            self.preview_player.play()
            return

        self._update_preview_status(position_ms)

    def _on_preview_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.preview_player.setPosition(int(self._trim_start_seconds * 1000))
            self.preview_player.play()

    def _on_preview_trim_changed(self) -> None:
        self._apply_preview_trim()
        self._update_preview_status(self.preview_player.position())
        self._apply_live_update()

    def _on_preview_muted_changed(self, muted: bool) -> None:
        self.preview_audio_output.setMuted(muted)
        self._apply_live_update()

    def _on_preview_playback_rate_changed(self, _value: int) -> None:
        self._apply_preview_direction()
        self._apply_live_update()

    def _apply_preview_trim(self) -> None:
        if self._preview_source is None:
            return

        trim_start = self._trim_start_seconds
        if self._preview_duration_seconds <= 0:
            return

        if 0 <= trim_start < self._preview_duration_seconds:
            self.preview_player.setPosition(int(trim_start * 1000))

    def _effective_preview_trim_end(self) -> float:
        trim_end = self._trim_end_seconds
        if trim_end <= 0:
            return 0.0
        if self._preview_duration_seconds <= 0:
            return trim_end
        return min(trim_end, self._preview_duration_seconds)

    def _update_preview_status(self, position_ms: int) -> None:
        if self._preview_source is None:
            return

        current_seconds = position_ms / 1000
        end_seconds = self._effective_preview_trim_end() or self._preview_duration_seconds
        self.preview_status_label.setText(
            f"{self._preview_source.name}  {current_seconds:.2f}s / {end_seconds:.2f}s"
        )

    def _show_video_preview(self, media_path: Path) -> None:
        if self._preview_movie is not None:
            self._preview_movie.stop()
            self._preview_movie = None
        self._preview_kind = "video"
        self.preview_image_item.setVisible(False)
        self.preview_video_item.setVisible(True)
        if self.preview_player.source().toLocalFile() != str(media_path):
            self._preview_duration_seconds = 0.0
            self.preview_player.setSource(QUrl.fromLocalFile(str(media_path)))
        self.preview_audio_output.setMuted(self.muted_checkbox.isChecked())
        self._apply_preview_direction()
        self._apply_preview_media_style()
        self._layout_preview_media_item()
        self.preview_play_button.setEnabled(True)
        self.preview_play_button.setText("Pause")
        self.preview_status_label.setText(f"Loading {media_path.name}...")
        self._update_trim_slider_window()
        self.preview_player.play()

    def _show_gif_preview(self, media_path: Path) -> None:
        self.preview_player.stop()
        self.preview_player.setSource(QUrl())
        self.preview_video_item.setVisible(False)
        self.preview_image_item.setVisible(True)
        self.preview_play_button.setEnabled(False)
        self.preview_play_button.setText("Play")
        self._preview_duration_seconds = 0.0
        self._preview_kind = "gif"
        self._update_trim_slider_window()

        if self._preview_movie is not None:
            self._preview_movie.stop()

        self._preview_movie = QMovie(str(media_path))
        self._preview_movie.setCacheMode(QMovie.CacheMode.CacheNone)
        qconnect(self._preview_movie.frameChanged, self._on_preview_movie_frame_changed)
        self._on_preview_movie_frame_changed()
        self._apply_preview_media_style()
        self._preview_movie.start()
        self.preview_status_label.setText(media_path.name)

    def _on_preview_movie_frame_changed(self, _frame: int | None = None) -> None:
        if self._preview_movie is None:
            return
        self.preview_image_item.setPixmap(self._preview_movie.currentPixmap())
        self._layout_preview_media_item()

    def _layout_preview_media_item(self, *_args: object) -> None:
        self._sync_preview_view_aspect()
        viewport_rect = self.preview_view.viewport().rect()
        scene_rect = self.preview_view.mapToScene(viewport_rect).boundingRect()
        self.preview_scene.setSceneRect(scene_rect)

        if self._preview_kind == "video" and self.preview_video_item.isVisible():
            native_size = self.preview_video_item.nativeSize()
            self._fit_preview_item(self.preview_video_item, native_size, scene_rect)
            return

        if self._preview_kind == "gif" and self.preview_image_item.isVisible():
            pixmap = self.preview_image_item.pixmap()
            if pixmap.isNull():
                self.preview_image_item.setPos(scene_rect.topLeft())
                return
            self._fit_preview_item(self.preview_image_item, QSizeF(pixmap.size()), scene_rect)

    def _fit_preview_item(self, item, native_size: QSizeF, scene_rect) -> None:
        if native_size.isEmpty():
            item.setPos(scene_rect.topLeft())
            if hasattr(item, "setSize"):
                item.setSize(scene_rect.size())
            return

        zoom = self._slider_value(self.zoom_slider, 100)
        scale = (
            max(
                scene_rect.width() / native_size.width(),
                scene_rect.height() / native_size.height(),
            )
            * zoom
        )
        target_width = native_size.width() * scale
        target_height = native_size.height() * scale
        x = scene_rect.left() + (scene_rect.width() - target_width) / 2
        y = scene_rect.top() + (scene_rect.height() - target_height) / 2
        item.setPos(QPointF(x, y))
        if hasattr(item, "setSize"):
            item.setSize(QSizeF(target_width, target_height))
        else:
            item.setScale(scale)

    def _apply_preview_media_style(self) -> None:
        active_item = None
        inactive_item = None
        if self._preview_kind == "video":
            active_item = self.preview_video_item
            inactive_item = self.preview_image_item
        elif self._preview_kind == "gif":
            active_item = self.preview_image_item
            inactive_item = self.preview_video_item

        if inactive_item is not None:
            inactive_item.setGraphicsEffect(None)
            inactive_item.setOpacity(1.0)

        if active_item is None:
            return

        active_item.setOpacity(self._slider_value(self.opacity_slider, 100))
        blur = self.blur_slider.value()
        if blur > 0:
            blur_effect = QGraphicsBlurEffect(self.preview_view)
            blur_effect.setBlurRadius(blur)
            active_item.setGraphicsEffect(blur_effect)
        else:
            active_item.setGraphicsEffect(None)

        self._layout_preview_media_item()

    def _connect_live_update_signals(self) -> None:
        qconnect(self.enabled_checkbox.toggled, self._apply_live_update)
        qconnect(self.theme_selector.currentIndexChanged, self._on_theme_changed)
        qconnect(self.media_selector.currentIndexChanged, self._on_media_selection_changed)
        qconnect(self.opacity_slider.valueChanged, self._on_preview_style_changed)
        qconnect(self.blur_slider.valueChanged, self._on_preview_style_changed)
        qconnect(self.zoom_slider.valueChanged, self._on_preview_style_changed)

        for checkbox in self.target_checkboxes.values():
            qconnect(checkbox.toggled, self._apply_live_update)

    def _on_media_selection_changed(self, _index: int) -> None:
        previous_identity = self._applied_media_identity
        if not self._confirm_current_media_selection_or_revert():
            return
        current_identity = self._current_media_identity()
        if current_identity != previous_identity:
            self._reset_trim_controls()
        self._applied_media_identity = current_identity
        self._apply_live_update()

    def _apply_live_update(self, *_args: object) -> None:
        staged = self._build_live_config(show_errors=False)
        if staged is None:
            return

        updated, resolved_media_path = staged
        self.config.data = self.config.normalize_data(updated)
        self.config.set_runtime_media_override(resolved_media_path if self._uses_external_source() else None)
        if self.on_live_update:
            self.on_live_update()

    def _on_theme_changed(self, _index: int) -> None:
        self._theme_mode = str(self.theme_selector.currentData() or "dark")
        self.setWindowIcon(create_brand_icon(self._theme_mode))
        self.header_logo.setPixmap(create_brand_pixmap(size=360, theme_mode=self._theme_mode))
        self._apply_site_palette()
        self._apply_live_update()

    def _on_preview_style_changed(self, _value: int) -> None:
        self._apply_preview_media_style()
        self._apply_live_update()

    def _build_live_config(self, *, show_errors: bool) -> tuple[dict[str, object], Path | None] | None:
        source_folder = self.folder_input.text().strip()
        selected_file = str(self.media_selector.currentData() or "")
        resolved_media_path: Path | None = None

        if source_folder:
            available_files = self._get_source_folder_files(source_folder)
            if selected_file:
                resolved_media_path = self.config.resolve_source_folder_media_path(
                    source_folder, selected_file
                )
            if selected_file and resolved_media_path is None:
                if show_errors:
                    showWarning("The selected media file was not found in the source folder.")
                return None
        elif selected_file:
            resolved_media_path = self.config.media_path(selected_file)
            if not resolved_media_path.is_file():
                selected_file = ""
                resolved_media_path = None
            if resolved_media_path is not None and not resolved_media_path.is_file():
                resolved_media_path = None

        updated = {
            "enabled": self.enabled_checkbox.isChecked(),
            "tutorial_seen": True,
            "theme_mode": str(self.theme_selector.currentData() or "dark"),
            "targets": {
                "reviewer": self.target_checkboxes["reviewer"].isChecked(),
                "deck_browser": self.target_checkboxes["deck_browser"].isChecked(),
                "main_window": self.target_checkboxes["main_window"].isChecked(),
            },
            "media": {
                "selected_file": selected_file,
                "source_folder": source_folder,
                "trim_start": round(self._trim_start_seconds, 2),
                "trim_end": round(self._trim_end_seconds, 2),
                "opacity": self._slider_value(self.opacity_slider, 100),
                "blur": self.blur_slider.value(),
                "zoom": self._slider_value(self.zoom_slider, 100),
                "muted": self.muted_checkbox.isChecked(),
                "playback_rate": self._slider_value(self.playback_rate_slider, 100),
            },
        }
        return self.config.normalize_data(updated), resolved_media_path

    def _make_slider(
        self,
        value: float,
        minimum: int,
        maximum: int,
        scale: int,
    ) -> tuple[QWidget, QSlider]:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(int(round(float(value) * scale)))

        label = QLabel(f"{slider.value() / scale:.2f}" if scale != 1 else str(slider.value()))
        label.setMinimumWidth(42)

        def update_label(slider_value: int, *, text: QLabel = label, factor: int = scale) -> None:
            text.setText(f"{slider_value / factor:.2f}" if factor != 1 else str(slider_value))

        qconnect(slider.valueChanged, update_label)

        layout.addWidget(slider)
        layout.addWidget(label)
        return container, slider

    def _slider_value(self, slider: QSlider, scale: int) -> float:
        return round(slider.value() / scale, 2)

    def _reset_slider(self, slider: QSlider, scale: int, media_key: str) -> None:
        default_value = DEFAULT_CONFIG["media"][media_key]
        slider.setValue(int(round(float(default_value) * scale)))

    def _reset_addon(self) -> None:
        confirmed = self._ask_confirmation(
            "Reset Add-on",
            "Reset all settings to first-run defaults?\n\n"
            "Imported media files will be removed when you click Save Settings.\n"
            "Click Cancel to discard this reset.",
        )
        if not confirmed:
            return

        self._reset_staged = True
        self._clear_preview("Reset staged — click Save Settings to apply")
        default_data = self.config.normalize_data(self.config.default_data())
        self.config.data = default_data
        self.config.clear_runtime_media_override()
        if self.on_live_update:
            self.on_live_update()
        self._load_config_into_form()
        showInfo("Reset staged. Click Save Settings to apply, or Cancel to discard.")

    def _load_config_into_form(self) -> None:
        self._invalidate_folder_cache()
        self._view_data = self.config.normalize_data(self.config.data)
        media_config = self._view_data.get("media", {})
        self._theme_mode = str(self._view_data.get("theme_mode", "dark"))
        self._trim_start_seconds = float(media_config.get("trim_start", 0.0))
        self._trim_end_seconds = float(media_config.get("trim_end", 0.0))
        self._trim_slider_max_seconds = max(self._trim_start_seconds, self._trim_end_seconds, 1.0)
        self._approved_large_media_paths.clear()
        widgets_to_block = [
            self.enabled_checkbox,
            self.theme_selector,
            self.media_selector,
            self.opacity_slider,
            self.blur_slider,
            self.zoom_slider,
            self.playback_rate_slider,
            self.trim_start_slider,
            self.trim_end_slider,
            self.muted_checkbox,
            *self.target_checkboxes.values(),
        ]
        for widget in widgets_to_block:
            widget.blockSignals(True)

        self.enabled_checkbox.setChecked(bool(self._view_data.get("enabled", True)))
        self.theme_selector.setCurrentIndex(max(0, self.theme_selector.findData(self._theme_mode)))
        for key, checkbox in self.target_checkboxes.items():
            checkbox.setChecked(
                bool(self._view_data.get("targets", {}).get(key, DEFAULT_CONFIG["targets"][key]))
            )

        self.folder_input.setText(str(media_config.get("source_folder", "")))
        self._refresh_media_selector(self._initial_selected_name())
        self.opacity_slider.setValue(int(round(float(media_config.get("opacity", 0.35)) * 100)))
        self.blur_slider.setValue(int(media_config.get("blur", 0)))
        self.zoom_slider.setValue(int(round(float(media_config.get("zoom", 1.0)) * 100)))
        self.playback_rate_slider.setValue(int(round(float(media_config.get("playback_rate", 1.0)) * 100)))
        self.muted_checkbox.setChecked(bool(media_config.get("muted", True)))
        self.trim_start_slider.setValue(int(round(self._trim_start_seconds * TRIM_SLIDER_SCALE)))
        self.trim_end_slider.setValue(
            self._trim_end_seconds_to_slider_value(self._trim_end_seconds, self.trim_end_slider.maximum())
        )

        for widget in widgets_to_block:
            widget.blockSignals(False)

        self.setWindowIcon(create_brand_icon(self._theme_mode))
        self.header_logo.setPixmap(create_brand_pixmap(size=360, theme_mode=self._theme_mode))
        self._apply_site_palette()
        self._update_trim_slider_window()
        self._commit_safe_state()
        self._applied_media_identity = self._current_media_identity()
        self._refresh_preview_with_guard(allow_prompt=False)

    def _apply_tooltips(self) -> None:
        self.enabled_checkbox.setToolTip(
            "Turns the animated background system on or off for all selected targets."
        )
        self.theme_selector.setToolTip("Switches the add-on dialog between dark and light palette variants.")
        self.media_selector.setToolTip(
            "Pick the currently staged background file from the selected source folder."
        )
        self.media_hint.setToolTip("Supported background formats for images, GIFs, and videos.")
        self.folder_input.setToolTip("Shows the external folder the add-on is reading media files from.")
        self.choose_folder_button.setToolTip(
            "Open a folder picker and load supported media files from that folder."
        )
        self.target_checkboxes["reviewer"].setToolTip("Show the background behind card reviews.")
        self.target_checkboxes["deck_browser"].setToolTip(
            "Show the background behind the deck browser screen."
        )
        self.target_checkboxes["main_window"].setToolTip("Show the background behind the overview screen.")
        self.opacity_slider.setToolTip(
            "Controls how strongly the background shows through the foreground content."
        )
        self.blur_slider.setToolTip("Adds blur to soften busy media behind your cards.")
        self.zoom_slider.setToolTip("Scales the background up to crop or fill more aggressively.")
        self.playback_rate_slider.setToolTip(
            "Speeds up or slows down video playback in the preview and live background."
        )
        self.trim_start_slider.setToolTip("Sets where video playback should begin in the loop.")
        self.trim_end_slider.setToolTip("Sets where video playback should end before looping back.")
        self.muted_checkbox.setToolTip("Keeps video backgrounds silent.")
        self.preview_play_button.setToolTip(
            "Play or pause the embedded preview without affecting the rest of Anki."
        )
        self.preview_view.setToolTip("")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_preview_media_item()

    def _confirm_current_media_selection_or_revert(self) -> bool:
        media_path = self._current_media_preview_path()
        if media_path is None or not media_path.is_file():
            self._commit_safe_state()
            self._clear_preview("Select media to preview")
            return True

        warning = self._large_media_warning(media_path)
        media_key = str(media_path)
        if warning and media_key not in self._approved_large_media_paths:
            confirmed = self._ask_confirmation("Large Background Media", warning)
            if not confirmed:
                self._restore_last_safe_state()
                return False
            self._approved_large_media_paths.add(media_key)

        self._commit_safe_state()
        self._refresh_preview()
        return True

    def _commit_safe_state(self) -> None:
        self._last_safe_source_folder = self.folder_input.text().strip()
        self._last_safe_media_selection = str(self.media_selector.currentData() or "")

    def _restore_last_safe_state(self) -> None:
        self.folder_input.setText(self._last_safe_source_folder)
        self._refresh_media_selector(self._last_safe_media_selection)
        self._refresh_preview_with_guard(allow_prompt=False)

    def _large_media_warning(self, media_path: Path) -> str:
        try:
            file_size = media_path.stat().st_size
        except OSError:
            return ""

        suffix = media_path.suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            threshold = LARGE_VIDEO_WARNING_BYTES
            media_label = "video"
        else:
            threshold = LARGE_GIF_WARNING_BYTES
            media_label = "GIF"

        if file_size < threshold:
            return ""

        return (
            f"The selected {media_label} is large ({self._format_file_size(file_size)}). "
            "This may cause performance issues, high memory usage, or instability in Anki.\n\n"
            "Do you want to keep using it anyway?"
        )

    def _format_file_size(self, size_bytes: int) -> str:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _ask_confirmation(self, title: str, message: str) -> bool:
        theme = LIGHT_THEME if self._theme_mode == "light" else DARK_THEME
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setWindowIcon(create_brand_icon(self._theme_mode))
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setStyleSheet(
            f"""
QMessageBox {{
    background: {theme["panel"]};
}}

QMessageBox QLabel {{
    color: {theme["text"]};
    background: transparent;
    min-width: 360px;
}}

QMessageBox QPushButton {{
    min-width: 88px;
    padding: 8px 16px;
    border: 1px solid {PALETTE_PURPLE_SOFT};
    background: {theme["button_fill"]};
    color: {theme["text"]};
}}

QMessageBox QPushButton:hover {{
    background: {theme["button_hover"]};
}}

QMessageBox QPushButton:pressed {{
    background: {theme["button_pressed"]};
}}
"""
        )
        return dialog.exec() == int(QMessageBox.StandardButton.Yes)

    def _open_support_link(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _on_trim_slider_changed(self, _value: int) -> None:
        start_seconds = self.trim_start_slider.value() / TRIM_SLIDER_SCALE
        end_seconds = self._trim_end_slider_to_seconds()

        if self.sender() is self.trim_start_slider and end_seconds and start_seconds > end_seconds:
            self.trim_end_slider.blockSignals(True)
            self.trim_end_slider.setValue(
                self._trim_end_seconds_to_slider_value(start_seconds, self.trim_end_slider.maximum())
            )
            self.trim_end_slider.blockSignals(False)
            end_seconds = start_seconds
        elif self.sender() is self.trim_end_slider and end_seconds and end_seconds < start_seconds:
            self.trim_start_slider.blockSignals(True)
            self.trim_start_slider.setValue(int(round(end_seconds * TRIM_SLIDER_SCALE)))
            self.trim_start_slider.blockSignals(False)
            start_seconds = end_seconds

        self._trim_start_seconds = round(start_seconds, 2)
        self._trim_end_seconds = round(end_seconds, 2)

        self._sync_trim_slider_labels()
        self._on_preview_trim_changed()

    def _reset_trim_controls(self) -> None:
        slider_max_seconds = self._preview_duration_seconds if self._preview_duration_seconds > 0 else 1.0
        self._trim_start_seconds = 0.0
        self._trim_end_seconds = 0.0
        self._trim_slider_max_seconds = slider_max_seconds
        slider_max = int(round(slider_max_seconds * TRIM_SLIDER_SCALE))
        self.trim_start_slider.blockSignals(True)
        self.trim_end_slider.blockSignals(True)
        self.trim_start_slider.setRange(0, slider_max)
        self.trim_end_slider.setRange(0, slider_max)
        self.trim_start_slider.setValue(0)
        self.trim_end_slider.setValue(slider_max)
        self.trim_start_slider.blockSignals(False)
        self.trim_end_slider.blockSignals(False)
        self._sync_trim_slider_labels()
        self._update_trim_slider_window()

    def _update_trim_slider_window(self) -> None:
        max_seconds = (
            self._preview_duration_seconds
            if self._preview_duration_seconds > 0
            else max(
                self._trim_start_seconds,
                self._trim_end_seconds,
                1.0,
            )
        )
        self._trim_slider_max_seconds = max_seconds
        slider_max = int(round(max_seconds * TRIM_SLIDER_SCALE))
        self.trim_start_slider.blockSignals(True)
        self.trim_end_slider.blockSignals(True)
        self.trim_start_slider.setRange(0, slider_max)
        self.trim_end_slider.setRange(0, slider_max)

        self._trim_start_seconds = min(self._trim_start_seconds, max_seconds)
        if self._trim_end_seconds > 0:
            self._trim_end_seconds = min(self._trim_end_seconds, max_seconds)
            if self._trim_end_seconds < self._trim_start_seconds:
                self._trim_end_seconds = self._trim_start_seconds

        if self._preview_source and self._preview_source.suffix.lower() in VIDEO_EXTENSIONS:
            duration_text = (
                f"Video duration: {self._preview_duration_seconds:.2f}s"
                if self._preview_duration_seconds > 0
                else "Loading video duration..."
            )
        else:
            duration_text = "Trim is used for video backgrounds"

        self.trim_range_label.setText(duration_text)
        self.trim_start_slider.setValue(int(round(self._trim_start_seconds * TRIM_SLIDER_SCALE)))
        self.trim_end_slider.setValue(
            self._trim_end_seconds_to_slider_value(self._trim_end_seconds, slider_max)
        )
        self.trim_start_slider.blockSignals(False)
        self.trim_end_slider.blockSignals(False)
        self._sync_trim_slider_labels()

    def _sync_trim_slider_labels(self) -> None:
        self.trim_range_start_label.setText(
            f"Start: {self.trim_start_slider.value() / TRIM_SLIDER_SCALE:.2f}s"
        )
        end_value = self._trim_end_slider_to_seconds()
        end_text = "Full media" if end_value <= 0 else f"{end_value:.2f}s"
        self.trim_range_end_label.setText(f"End: {end_text}")

    def _trim_end_slider_to_seconds(self) -> float:
        slider_value = self.trim_end_slider.value()
        if slider_value >= self.trim_end_slider.maximum():
            return 0.0
        return round(max(slider_value / TRIM_SLIDER_SCALE, 0.01), 2)

    def _trim_end_seconds_to_slider_value(self, end_seconds: float, slider_max: int) -> int:
        if end_seconds <= 0:
            return slider_max
        return max(1, min(slider_max, int(round(end_seconds * TRIM_SLIDER_SCALE))))

    def _uses_external_source(self) -> bool:
        return bool(self.folder_input.text().strip())

    def _sync_preview_view_aspect(self) -> None:
        if not hasattr(self, "preview_view"):
            return
        width = max(320, self.preview_view.viewport().width() or PREVIEW_MAX_WIDTH)
        height = max(180, round(width * 9 / 16))
        self.preview_view.setMinimumHeight(height)

    def _apply_preview_direction(self) -> None:
        playback_rate = self._slider_value(self.playback_rate_slider, 100)
        self.preview_player.setPlaybackRate(playback_rate)

    def _apply_site_palette(self) -> None:
        theme = LIGHT_THEME if self._theme_mode == "light" else DARK_THEME
        self.setStyleSheet(
            f"""
QDialog#animatedBackgroundDialog {{
    background: {theme["ink"]};
    color: {theme["text"]};
}}

QDialog#animatedBackgroundDialog QWidget {{
    color: {theme["text"]};
    font-size: 13px;
    font-family: "Segoe UI", Arial, sans-serif;
}}

QDialog#animatedBackgroundDialog QFrame#topHeader {{
    background: transparent;
    border: 0;
}}

QDialog#animatedBackgroundDialog QLabel#dialogLogo {{
    min-height: 150px;
    padding: 0;
}}

QDialog#animatedBackgroundDialog QLabel#enabledSwitchLabel {{
    color: {theme["text"]};
    font-size: 15px;
    font-weight: 600;
}}

QDialog#animatedBackgroundDialog QGroupBox {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {theme["panel"]},
        stop:1 {theme["panel_alt"]});
    border: 1px solid {theme["border"]};
    border-radius: 0px;
    margin-top: 18px;
    padding: 18px 14px 14px 14px;
    font-weight: 700;
}}

QDialog#animatedBackgroundDialog QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: {PALETTE_PURPLE_SOFT};
    font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
    font-size: 18px;
    letter-spacing: 0.03em;
}}

QDialog#animatedBackgroundDialog QFrame#brandHeader {{
    border-bottom: 1px solid {theme["border"]};
    padding-bottom: 10px;
    margin-bottom: 4px;
}}

QDialog#animatedBackgroundDialog QLabel#brandMark {{
    min-width: 52px;
    min-height: 52px;
    max-width: 52px;
    max-height: 52px;
    background: {theme["panel"]};
    border: 2px solid {PALETTE_PURPLE_SOFT};
    color: {PALETTE_CYAN};
    font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
    font-size: 18px;
    letter-spacing: 0.06em;
}}

QDialog#animatedBackgroundDialog QLabel#brandTitle {{
    color: {theme["text"]};
    font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
    font-size: 28px;
}}

QDialog#animatedBackgroundDialog QLabel#brandSubtitle,
QDialog#animatedBackgroundDialog QLabel#mediaHintLabel,
QDialog#animatedBackgroundDialog QLabel#previewStatusLabel,
QDialog#animatedBackgroundDialog QLabel#trimMetaLabel,
QDialog#animatedBackgroundDialog QLabel#previewCardStatusLabel {{
    color: {theme["muted"]};
}}

QDialog#animatedBackgroundDialog QLabel#trimStartLabel {{
    color: {PALETTE_GREEN};
    font-weight: 600;
}}

QDialog#animatedBackgroundDialog QLabel#trimEndLabel {{
    color: {PALETTE_AMBER};
    font-weight: 600;
}}

QDialog#animatedBackgroundDialog QLineEdit,
QDialog#animatedBackgroundDialog QComboBox {{
    background: {theme["input_bg"]};
    border: 1px solid {theme["border"]};
    border-radius: 0px;
    padding: 8px 10px;
    selection-background-color: {PALETTE_BLUE};
}}

QDialog#animatedBackgroundDialog QLineEdit:focus,
QDialog#animatedBackgroundDialog QComboBox:focus {{
    border: 1px solid {PALETTE_CYAN};
}}

QDialog#animatedBackgroundDialog QComboBox::drop-down {{
    border: 0;
    width: 28px;
}}

QDialog#animatedBackgroundDialog QComboBox QAbstractItemView {{
    background: {theme["panel"]};
    border: 1px solid {theme["border"]};
    selection-background-color: {theme["selection"]};
    selection-color: {theme["text"]};
}}

QDialog#animatedBackgroundDialog QPushButton {{
    background: {theme["button_fill"]};
    color: {theme["text"]};
    border: 1px solid {PALETTE_PURPLE_SOFT};
    border-radius: 0px;
    padding: 8px 14px;
    font-weight: 600;
}}

QDialog#animatedBackgroundDialog QPushButton:hover {{
    background: {theme["button_hover"]};
}}

QDialog#animatedBackgroundDialog QPushButton:pressed {{
    background: {theme["button_pressed"]};
}}

QDialog#animatedBackgroundDialog QPushButton#smallResetButton {{
    min-width: 72px;
    padding: 6px 10px;
    border: 1px solid {theme["border"]};
    color: {theme["muted"]};
}}

QDialog#animatedBackgroundDialog QPushButton#supportButton {{
    min-width: 154px;
    padding: 11px 18px;
    font-size: 15px;
}}

QDialog#animatedBackgroundDialog QMenu {{
    background: {theme["panel"]};
    color: {theme["text"]};
    border: 1px solid {theme["border"]};
    padding: 6px 0;
}}

QDialog#animatedBackgroundDialog QMenu::item {{
    padding: 8px 18px;
    background: transparent;
    color: {theme["text"]};
}}

QDialog#animatedBackgroundDialog QMenu::item:selected {{
    background: {theme["selection"]};
    color: {theme["text"]};
}}

QDialog#animatedBackgroundDialog QCheckBox#enabledSwitch {{
    spacing: 0;
}}

QDialog#animatedBackgroundDialog QCheckBox#enabledSwitch::indicator {{
    width: 52px;
    height: 30px;
    border-radius: 15px;
    border: 1px solid {theme["border"]};
    background: {theme["slider_groove"]};
}}

QDialog#animatedBackgroundDialog QCheckBox#enabledSwitch::indicator:checked {{
    background: {PALETTE_GREEN};
    border: 1px solid {PALETTE_GREEN};
}}

QDialog#animatedBackgroundDialog QPushButton#smallResetButton:hover {{
    border: 1px solid {PALETTE_PURPLE_SOFT};
    color: {PALETTE_TEXT};
}}

QDialog#animatedBackgroundDialog QDialogButtonBox QPushButton {{
    min-width: 92px;
}}

QDialog#animatedBackgroundDialog QCheckBox {{
    spacing: 10px;
    color: {theme["text"]};
}}

QDialog#animatedBackgroundDialog QSlider::groove:horizontal {{
    height: 6px;
    border-radius: 0px;
    background: {theme["slider_groove"]};
}}

QDialog#animatedBackgroundDialog QSlider::handle:horizontal {{
    width: 16px;
    margin: -6px 0;
    border-radius: 0px;
    background: {PALETTE_PURPLE_SOFT};
    border: 1px solid {theme["ink"]};
}}

QDialog#animatedBackgroundDialog QSlider#trimStartSlider::handle:horizontal {{
    background: {PALETTE_PURPLE};
}}

QDialog#animatedBackgroundDialog QSlider#trimEndSlider::handle:horizontal {{
    background: {PALETTE_PURPLE_DEEP};
}}
"""
        )
