from aqt import gui_hooks, mw, qconnect
from aqt.webview import AnkiWebView
from aqt.qt import QAction, QApplication

from .src.common.constants import ADDON_CONSTANTS
from .src.common.utils import ensure_main_window
from .src.config.config_manager import ConfigManager
from .src.injector.background_controller import BackgroundController
from .src.injector.webview_injector import WebviewInjector
from .src.view.settings_dialog import SettingsDialog


class AnimatedBackgroundAddon:
    def __init__(self) -> None:
        self.config = ConfigManager()
        self.injector = WebviewInjector(self.config)
        self.background_controller = BackgroundController(self.config, self.injector)
        self._settings_dialog: SettingsDialog | None = None

        if mw:
            mw.addonManager.setWebExports(__name__, r"(user_files|assets)/.*\.(gif|png|jpg|jpeg|webm|mp4)")

        app = QApplication.instance()
        if app:
            qconnect(app.aboutToQuit, self._close_settings_dialog_for_shutdown)

        gui_hooks.webview_will_set_content.append(self.injector.on_webview_will_set_content)
        gui_hooks.profile_did_open.append(self._on_profile_did_open)
        gui_hooks.state_did_change.append(self.background_controller.on_state_did_change)
        gui_hooks.card_review_webview_did_init.append(self._allow_background_video_autoplay)
        gui_hooks.deck_browser_did_render.append(self._allow_deck_browser_video_autoplay)
        gui_hooks.overview_did_refresh.append(self._allow_overview_video_autoplay)
        gui_hooks.deck_browser_did_render.append(self._on_screen_did_render)
        gui_hooks.overview_did_refresh.append(self._on_screen_did_render)
        gui_hooks.reviewer_did_show_question.append(self._on_reviewer_did_show_question)

        main_window = ensure_main_window()
        self.action = QAction(ADDON_CONSTANTS.MENU_LABEL.value, main_window)
        qconnect(self.action.triggered, self._open_settings)

        if mw:
            mw.form.menuTools.addAction(self.action)

    def _open_settings(self) -> None:
        main_window = ensure_main_window()
        if not main_window:
            return

        if self._settings_dialog is not None:
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        dialog = SettingsDialog(self.config, self._on_live_settings_changed, parent=main_window)
        self._settings_dialog = dialog
        qconnect(dialog.destroyed, self._clear_settings_dialog_reference)

        if dialog.exec():
            self.config.save()
            self.background_controller.refresh_current_view()

        if self._settings_dialog is dialog:
            self._settings_dialog = None

    def _allow_background_video_autoplay(self, webview: AnkiWebView, *_args) -> None:
        webview.setPlaybackRequiresGesture(False)

    def _allow_deck_browser_video_autoplay(self, deck_browser) -> None:
        deck_browser.web.setPlaybackRequiresGesture(False)

    def _allow_overview_video_autoplay(self, overview) -> None:
        overview.web.setPlaybackRequiresGesture(False)

    def _on_profile_did_open(self) -> None:
        self.config.reload()
        self.background_controller.refresh_current_view()

    def _on_live_settings_changed(self) -> None:
        self.background_controller.refresh_current_view()

    def _clear_settings_dialog_reference(self, *_args) -> None:
        self._settings_dialog = None

    def _close_settings_dialog_for_shutdown(self) -> None:
        if self._settings_dialog is None:
            return
        self._settings_dialog.close()

    def _on_screen_did_render(self, *_args) -> None:
        self.background_controller.refresh_current_view()

    def _on_reviewer_did_show_question(self, _card) -> None:
        self.background_controller.refresh_current_view()


addon = AnimatedBackgroundAddon()
