from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from aqt import mw
from aqt.qt import QUrl
from aqt.webview import WebContent

from ..config.config_manager import ConfigManager

CONTEXT_TARGETS = {
    "DeckBrowser": "deck_browser",
    "Overview": "main_window",
}
VIDEO_EXTENSIONS = {".mp4", ".webm"}


class WebviewInjector:
    def __init__(self, config: ConfigManager) -> None:
        self.config = config
        self._addon_package = ""

    def on_webview_will_set_content(self, web_content: WebContent, context: Any) -> None:
        target = self._resolve_target(context)
        if not target:
            return

        config_data = self.config.data
        if not config_data.get("enabled", False):
            return

        if not config_data.get("targets", {}).get(target, False):
            return

        media_config = config_data.get("media", {})
        media_path = self.config.resolve_media_path(media_config)
        if media_path is None:
            return

        media_url = self._build_media_url(media_path)
        if not media_url:
            return

        css = self._build_css(media_config)
        web_content.head += f"\n<style>{css}</style>"

        if media_path.suffix.lower() in VIDEO_EXTENSIONS:
            return

        html_snippet = self._build_html(media_url)
        web_content.body = html_snippet + web_content.body

    def _resolve_target(self, context: Any) -> str | None:
        context_name = type(context).__name__
        if context_name.startswith("Reviewer"):
            return "reviewer"

        return CONTEXT_TARGETS.get(context_name)

    def _build_media_url(self, media_path: Path) -> str:
        if not self._addon_package and mw:
            self._addon_package = mw.addonManager.addonFromModule(__name__)

        if self._addon_package:
            try:
                relative_path = media_path.relative_to(self.config.addon_root).as_posix()
                return f"/_addons/{self._addon_package}/{relative_path}"
            except ValueError:
                pass

        return QUrl.fromLocalFile(str(media_path)).toString()

    def _build_css(self, media_config: dict[str, Any]) -> str:
        opacity = self._clamp_float(media_config.get("opacity", 0.35), 0.0, 1.0)
        blur = self._clamp_int(media_config.get("blur", 0), 0, 24)
        zoom = self._clamp_float(media_config.get("zoom", 1.0), 1.0, 1.6)

        return f"""
html,
body {{
    background: transparent !important;
}}

#animated-background-media-root {{
    position: fixed;
    inset: 0;
    z-index: -1;
    pointer-events: none;
    overflow: hidden;
}}

#animated-background-media-root img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: {opacity};
    filter: blur({blur}px);
    transform: scale({zoom});
}}
"""

    def _build_html(self, media_url: str) -> str:
        escaped_url = html.escape(media_url, quote=True)
        return (
            '<div id="animated-background-media-root">'
            f'<img id="animated-background-media" src="{escaped_url}" alt="Animated background"></div>'
        )

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
