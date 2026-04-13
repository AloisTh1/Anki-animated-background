# AnkiAnimatedBackground Architecture

## Runtime Shape

The add-on is intentionally small and direct:

- `__init__.py`
  Registers Anki hooks and the Tools menu action.
- `src/config/config_manager.py`
  Loads, normalizes, and saves profile-scoped settings, migrates legacy `user_files`, and manages committed media files.
- `src/injector/webview_injector.py`
  Detects supported webview contexts and injects a fixed `<img>` or `<video>` background layer.
- `src/view/settings_dialog.py`
  Renders the settings dialog, stages external media for live preview, and commits media on save.

## Flow

1. Anki loads the add-on entry point.
2. The add-on creates a shared `ConfigManager`.
3. `WebviewInjector` reads config on each render and injects the selected media background.
4. The settings dialog edits the live config dictionary and can temporarily override the active media path.
5. Saving commits the chosen media into the profile media directory and writes the normalized config to profile add-on data.

## Supported Targets

- Reviewer
- Deck Browser
- Overview

## Media Model

Imported media is stored in:

- `<profile>/addon_data/AnkiAnimatedBackground/media/`

Packaged defaults are stored in:

- `assets/default_media/Wallpapers_anki/`

Supported formats:

- `gif`
- `png`
- `jpg` / `jpeg`
- `webm`
- `mp4`
