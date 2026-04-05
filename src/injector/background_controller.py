from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aqt import colors, mw
from aqt.qt import (
    QEvent,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsScene,
    QGraphicsView,
    QObject,
    QPointF,
    QSizeF,
    Qt,
    QTimer,
    qconnect,
)
from aqt.theme import theme_manager
from aqt.webview import AnkiWebView
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem

from ..config.config_manager import ConfigManager
from .webview_injector import VIDEO_EXTENSIONS, WebviewInjector

REVERSE_STEP_INTERVAL_MS = 33
REVERSE_SEEK_GUARD_MS = REVERSE_STEP_INTERVAL_MS * 2

STATE_TO_TARGET = {
    "review": "reviewer",
    "deckBrowser": "deck_browser",
    "overview": "main_window",
}


class NativeVideoBackground(QObject):
    def __init__(self, webview: AnkiWebView, on_error: Any = None) -> None:
        super().__init__(webview)
        self.webview = webview
        self._source: Path | None = None
        self._duration_seconds = 0.0
        self._trim_start = 0.0
        self._trim_end = 0.0
        self._zoom = 1.0
        self._bounce = False
        self._direction = 1
        self._playback_rate = 1.0
        self._on_error = on_error
        self._has_error = False
        self._last_reverse_target_ms: int | None = None

        parent = webview.parentWidget()
        if parent is None:
            raise RuntimeError("Anki webview parent widget is required for native video backgrounds.")

        self.view = QGraphicsView(parent)
        self.view.setObjectName("animated-background-native-video")
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setInteractive(False)
        self.view.setStyleSheet("background: transparent; border: 0;")
        self.view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.view.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.scene = QGraphicsScene(self.view)
        self.scene.setBackgroundBrush(QColor(0, 0, 0, 0))
        self.view.setScene(self.scene)

        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self._blur_effect: QGraphicsBlurEffect | None = None

        self.audio_output = QAudioOutput(self.view)
        self.player = QMediaPlayer(self.view)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_item)

        self._reverse_timer = QTimer(self.view)
        self._reverse_timer.setInterval(REVERSE_STEP_INTERVAL_MS)
        qconnect(self._reverse_timer.timeout, self._on_reverse_tick)

        qconnect(self.player.positionChanged, self._on_position_changed)
        qconnect(self.player.durationChanged, self._on_duration_changed)
        qconnect(self.player.mediaStatusChanged, self._on_media_status_changed)
        qconnect(self.player.errorOccurred, self._on_error_occurred)
        qconnect(self.video_item.nativeSizeChanged, self._sync_video_geometry)

        self.webview.installEventFilter(self)
        self.hide()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.webview and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
            QEvent.Type.Hide,
        }:
            self._sync_geometry()
        return super().eventFilter(watched, event)

    def has_error(self) -> bool:
        return self._has_error

    def show_for(self, media_path: Path, media_config: dict[str, Any]) -> None:
        resolved = media_path.resolve()
        previous_trim_start = self._trim_start
        previous_trim_end = self._trim_end
        if self._source != resolved:
            self._has_error = False
            self._source = resolved
            self._duration_seconds = 0.0
            self._direction = 1
            self.player.setSource(QUrl.fromLocalFile(str(resolved)))

        self._trim_start = self._clamp_float(media_config.get("trim_start", 0.0), 0.0, 86_400.0)
        self._trim_end = self._clamp_float(media_config.get("trim_end", 0.0), 0.0, 86_400.0)
        self._zoom = self._clamp_float(media_config.get("zoom", 1.0), 1.0, 1.6)
        self._bounce = bool(media_config.get("bounce", False))
        self._playback_rate = self._clamp_float(media_config.get("playback_rate", 1.0), 0.25, 3.0)

        self.audio_output.setMuted(bool(media_config.get("muted", True)))
        if not self._bounce:
            self._direction = 1
        self._apply_playback_direction()
        self.video_item.setOpacity(self._clamp_float(media_config.get("opacity", 0.35), 0.0, 1.0))
        self._set_blur(self._clamp_int(media_config.get("blur", 0), 0, 24))

        if self._source == resolved and (
            previous_trim_start != self._trim_start or previous_trim_end != self._trim_end
        ):
            self._sync_playback_to_trim_window()

        self._sync_geometry()
        self.view.show()
        self.view.lower()
        self.webview.raise_()
        self.player.play()

    def hide(self) -> None:
        self._reverse_timer.stop()
        self._direction = 1
        self._last_reverse_target_ms = None
        self.player.stop()
        self.view.hide()

    def _set_blur(self, blur: int) -> None:
        if blur <= 0:
            if self._blur_effect is not None:
                self.video_item.setGraphicsEffect(None)
                self._blur_effect = None
            return

        if self._blur_effect is None:
            self._blur_effect = QGraphicsBlurEffect(self.view)
            self.video_item.setGraphicsEffect(self._blur_effect)
        self._blur_effect.setBlurRadius(blur)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_seconds = max(0.0, duration_ms / 1000)
        self._seek_to_trim_start()
        self._sync_video_geometry()

    def _on_position_changed(self, position_ms: int) -> None:
        if self._direction < 0:
            if (
                self._last_reverse_target_ms is not None
                and abs(position_ms - self._last_reverse_target_ms) <= REVERSE_SEEK_GUARD_MS
            ):
                self._last_reverse_target_ms = None
            return

        current_seconds = position_ms / 1000
        if self._bounce:
            trim_end = self._effective_trim_end() or self._duration_seconds
            if trim_end > self._trim_start and current_seconds >= trim_end:
                self._start_reverse()
                return

        effective_trim_end = self._effective_trim_end()
        if effective_trim_end > self._trim_start and current_seconds >= effective_trim_end:
            self.player.setPosition(int(self._trim_start * 1000))
            self.player.play()

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._bounce:
            self._start_reverse()
            return
        self.player.setPosition(int(self._trim_start * 1000))
        self.player.play()

    def _start_reverse(self) -> None:
        end_seconds = self._effective_trim_end() or self._duration_seconds
        if end_seconds <= self._trim_start:
            self.player.setPosition(int(self._trim_start * 1000))
            self._direction = 1
            self._apply_playback_direction()
            self.player.play()
            return

        self._direction = -1
        self.player.setPosition(int(end_seconds * 1000))
        self._apply_playback_direction()

    def _on_reverse_tick(self) -> None:
        step_ms = max(1, int(REVERSE_STEP_INTERVAL_MS * self._playback_rate))
        current_ms = self.player.position()
        target_ms = current_ms - step_ms
        start_ms = int(self._trim_start * 1000)

        if target_ms <= start_ms:
            self._reverse_timer.stop()
            self._direction = 1
            self._last_reverse_target_ms = None
            self.player.setPosition(start_ms)
            self._apply_playback_direction()
            self.player.play()
            return

        self._last_reverse_target_ms = target_ms
        self.player.setPosition(target_ms)

    def _on_error_occurred(self, error: QMediaPlayer.Error, message: str = "") -> None:
        self._has_error = True
        self.hide()
        if self._on_error:
            self._on_error()

    def _seek_to_trim_start(self) -> None:
        if self._trim_start <= 0 or self._duration_seconds <= 0:
            return
        if self._trim_start < self._duration_seconds:
            self.player.setPosition(int(self._trim_start * 1000))

    def _effective_trim_end(self) -> float:
        if self._trim_end <= 0:
            return 0.0
        if self._duration_seconds <= 0:
            return self._trim_end
        return min(self._trim_end, self._duration_seconds)

    def _sync_playback_to_trim_window(self) -> None:
        if self._duration_seconds <= 0:
            return

        if self._bounce:
            self._direction = 1
            self._apply_playback_direction()

        current_seconds = self.player.position() / 1000
        effective_trim_end = self._effective_trim_end()
        if current_seconds < self._trim_start or (
            effective_trim_end > self._trim_start and current_seconds >= effective_trim_end
        ):
            self.player.setPosition(int(self._trim_start * 1000))

    def _sync_geometry(self, *_args: object) -> None:
        if self.webview.parentWidget() is None:
            return

        self.view.setGeometry(self.webview.geometry())
        if self.webview.isHidden():
            self.view.hide()
            return

        if self._source is not None:
            self.view.lower()
            self.webview.raise_()
        self._sync_video_geometry()

    def _sync_video_geometry(self, *_args: object) -> None:
        viewport_rect = self.view.viewport().rect()
        scene_rect = self.view.mapToScene(viewport_rect).boundingRect()
        self.scene.setSceneRect(scene_rect)

        native_size = self.video_item.nativeSize()
        if native_size.isEmpty():
            self.video_item.setPos(scene_rect.topLeft())
            self.video_item.setSize(scene_rect.size())
            return

        scale = (
            max(
                scene_rect.width() / native_size.width(),
                scene_rect.height() / native_size.height(),
            )
            * self._zoom
        )
        target_size = QSizeF(native_size.width() * scale, native_size.height() * scale)
        x = scene_rect.left() + (scene_rect.width() - target_size.width()) / 2
        y = scene_rect.top() + (scene_rect.height() - target_size.height()) / 2
        self.video_item.setPos(QPointF(x, y))
        self.video_item.setSize(target_size)

    def _clamp_float(self, value: object, minimum: float, maximum: float) -> float:
        try:
            return max(minimum, min(maximum, float(value)))
        except (TypeError, ValueError):
            return minimum

    def _clamp_int(self, value: object, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(maximum, int(value)))
        except (TypeError, ValueError):
            return minimum

    def _apply_playback_direction(self) -> None:
        if self._direction < 0:
            self.player.pause()
            self.player.setPlaybackRate(self._playback_rate)
            if not self._reverse_timer.isActive():
                self._reverse_timer.start()
            return

        self._reverse_timer.stop()
        self._last_reverse_target_ms = None
        self.player.setPlaybackRate(self._playback_rate)


class BackgroundController:
    def __init__(self, config: ConfigManager, injector: WebviewInjector) -> None:
        self.config = config
        self.injector = injector
        self.main_webview = mw.web if mw else None
        self.native_video = (
            NativeVideoBackground(self.main_webview, on_error=self._on_video_error)
            if self.main_webview
            else None
        )

    def refresh_current_view(self) -> None:
        if not self.main_webview:
            return

        target = self._infer_target_from_state()
        if not target or not self._target_enabled(target):
            self._deactivate_background()
            return

        media_config = self.config.data.get("media", {})
        media_path = self.config.resolve_media_path(media_config)
        if media_path is None:
            self._deactivate_background()
            return

        if media_path.suffix.lower() in VIDEO_EXTENSIONS:
            if self.native_video and self.native_video.has_error():
                self._deactivate_background()
                return
            self._set_webview_transparency(True)
            self._inject_live_style(media_config)
            self._remove_injected_media_root()
            if self.native_video:
                self.native_video.show_for(media_path, media_config)
            return

        self._hide_native_video()
        media_url = self.injector._build_media_url(media_path)
        if media_url:
            self._set_webview_transparency(True)
            self._inject_live_image(media_url, media_config)
        else:
            self._set_webview_transparency(False)

    def on_state_did_change(self, new_state: str, old_state: str) -> None:
        self.refresh_current_view()

    def _on_video_error(self) -> None:
        self._deactivate_background()

    def _deactivate_background(self) -> None:
        self._clear_current_page()
        self._hide_native_video()
        self._set_webview_transparency(False)

    def _inject_live_style(self, media_config: dict[str, Any]) -> None:
        if not self.main_webview:
            return

        css = self.injector._build_css(media_config)
        script = f"""
(() => {{
    let style = document.getElementById("animated-background-media-style");
    if (!style) {{
        style = document.createElement("style");
        style.id = "animated-background-media-style";
        document.head.appendChild(style);
    }}
    style.textContent = {json.dumps(css)};
}})();
""".strip()
        self.main_webview.eval(script)

    def _inject_live_image(self, media_url: str, media_config: dict[str, Any]) -> None:
        if not self.main_webview:
            return

        self._inject_live_style(media_config)
        html_snippet = self.injector._build_html(media_url, False, media_config)
        script = f"""
(() => {{
    const existing = document.getElementById("animated-background-media-root");
    if (existing) {{
        existing.remove();
    }}

    document.body.insertAdjacentHTML("afterbegin", {json.dumps(html_snippet)});
}})();
""".strip()
        self.main_webview.eval(script)

    def _remove_injected_media_root(self) -> None:
        if not self.main_webview:
            return
        self.main_webview.eval(
            """
(() => {
    const existing = document.getElementById("animated-background-media-root");
    if (existing) {
        existing.remove();
    }
})();
""".strip()
        )

    def _clear_current_page(self) -> None:
        if not self.main_webview:
            return
        self.main_webview.eval(
            """
(() => {
    const existing = document.getElementById("animated-background-media-root");
    if (existing) {
        existing.remove();
    }

    const style = document.getElementById("animated-background-media-style");
    if (style) {
        style.textContent = "";
    }
})();
""".strip()
        )

    def _hide_native_video(self) -> None:
        if self.native_video:
            self.native_video.hide()

    def _set_webview_transparency(self, transparent: bool) -> None:
        if not self.main_webview:
            return

        background = QColor(0, 0, 0, 0) if transparent else theme_manager.qcolor(colors.CANVAS)
        self.main_webview.page().setBackgroundColor(background)
        self.main_webview.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, transparent)
        self.main_webview.setStyleSheet("background: transparent;" if transparent else "")

    def _target_enabled(self, target: str) -> bool:
        if not bool(self.config.data.get("enabled", False)):
            return False
        return bool(self.config.data.get("targets", {}).get(target, False))

    def _infer_target_from_state(self) -> str | None:
        if not mw:
            return None
        return STATE_TO_TARGET.get(getattr(mw, "state", ""))
