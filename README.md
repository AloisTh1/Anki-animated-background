# AnkiAnimatedBackground

<p align="center">
  <img src="assets/packaging/logo_normal.png" alt="AnkiAnimatedBackground logo" width="220" />
</p>

<p align="center">
  Animated image and video backgrounds for Anki, with live preview and per-screen controls.
</p>

<p align="center">
  <img src="preview.png" alt="Animated Background settings preview" width="900" />
</p>

## Overview

AnkiAnimatedBackground adds animated or static backgrounds to Anki's core study surfaces while keeping the add-on workflow focused on real usage:

- Reviewer support for card study sessions
- Deck Browser support for navigation and deck selection
- Overview support for deck landing pages
- Live preview in the settings dialog before saving changes
- Support for packaged sample media and user-selected local folders
- Controls for opacity, blur, zoom, trim, mute, bounce, and playback speed

Supported media formats:

- `gif`
- `png`
- `jpg`
- `jpeg`
- `webm`
- `mp4`

## Tutorial

### Install

1. Build or download the `.ankiaddon` package.
2. Open Anki.
3. Go to `Tools -> Add-ons`.
4. Drag the `.ankiaddon` file into the Add-ons window.
5. Restart Anki.

### First Run

1. Open `Tools -> Animated Background`.
2. Leave the packaged sample selected, or choose your own source folder.
3. Pick which screens should receive the background:
   - Reviewer
   - Deck Browser
   - Overview
4. Adjust the display controls:
   - Opacity
   - Blur
   - Zoom
   - Playback rate
   - Trim start / trim end
   - Mute
   - Bounce
5. Watch the live preview panel to confirm the result.
6. Click `Save Settings`.

### Everyday Use

- Use packaged media for a zero-setup experience.
- Use your own local folder if you want to browse a personal wallpaper collection.
- If playback feels heavy, reduce video size, lower blur, or switch to a smaller file.
- If a file becomes unavailable, reopen settings and pick a valid source again.

## Architecture

The add-on is intentionally split into a few small modules with clear roles:

- `__init__.py`
  Bootstraps the add-on, registers hooks, and exposes the settings dialog through Anki's Tools menu.
- `src/config/config_manager.py`
  Owns config normalization, persistence, managed media handling, and source-folder resolution.
- `src/injector/webview_injector.py`
  Injects image-based backgrounds and CSS into supported Anki webviews.
- `src/injector/background_controller.py`
  Coordinates live background activation, native video playback, screen-state refresh, and cleanup.
- `src/view/settings_dialog.py`
  Hosts the user workflow for selection, preview, tuning, reset, and save.

### Mermaid Flow

```mermaid
flowchart TD
    subgraph ANKI["Anki Native Runtime"]
        A[Anki startup]
        B[Main window / mw]
        C[Reviewer, Deck Browser, Overview]
        D[Qt WebView]
        E[Qt Multimedia backend]
    end

    subgraph ADDON["Animated Background Add-on"]
        F[__init__.py<br/>entry point + hook registration]
        G[ConfigManager<br/>normalize + resolve + persist]
        H[SettingsDialog<br/>user controls + preview]
        I[WebviewInjector<br/>HTML/CSS image injection]
        J[BackgroundController<br/>screen-state coordinator]
        K[NativeVideoBackground<br/>QMediaPlayer + overlay]
    end

    subgraph DATA["Add-on Data"]
        L[user_files/config.json]
        M[user_files/media/]
        N[Packaged sample media]
    end

    A -->|"loads add-on"| F
    A -->|"creates Anki UI"| B
    B -->|"hosts screens"| C
    C -->|"renders into"| D
    F -->|"registers hooks on"| B
    F -->|"creates shared services"| G
    F -->|"creates"| I
    F -->|"creates"| J
    F -->|"opens from Tools menu"| H

    G -->|"reads / writes"| L
    G -->|"resolves managed files from"| M
    G -->|"resolves packaged defaults from"| N

    H -->|"loads current settings from"| G
    H -->|"live preview / staged updates to"| J
    H -->|"save persists through"| G

    I -->|"injects CSS / IMG background into"| D
    J -->|"checks active screen + media config in"| G
    J -->|"for image media, delegates render to"| I
    J -->|"for video media, controls"| K
    K -->|"plays video using"| E
    K -->|"draws native overlay above"| D

    C -->|"screen change hooks trigger refresh in"| J
    D -->|"shows image background path"| I
    E -->|"drives playback status / errors for"| K

    classDef anki fill:#eef2f7,stroke:#5f6b7a,color:#1a2230
    classDef addon fill:#f6f1ff,stroke:#7b61ff,color:#241b4b
    classDef data fill:#eefaf4,stroke:#34a853,color:#163322
    classDef imagePath fill:#fff5e8,stroke:#ff9800,color:#4a2a00
    classDef videoPath fill:#e9f4ff,stroke:#1e88e5,color:#0d2a4d

    class A,B,C,D,E anki
    class F,G,H,J addon
    class L,M,N data
    class I imagePath
    class K videoPath
```

### Design Patterns

- Single source of truth:
  `ConfigManager` owns normalized runtime configuration and media-path resolution.
- Controller pattern:
  `BackgroundController` decides when backgrounds should appear, disappear, or fail closed.
- Strategy split by media type:
  image backgrounds are webview-injected, while video backgrounds use native Qt playback.
- Staged editing workflow:
  the settings dialog lets the user preview and tune values before persisting them.
- Defensive path handling:
  media resolution stays rooted to the add-on or the chosen source folder to avoid path escapes.

## Project Layout

```text
AnkiAnimatedBackground/
|-- __init__.py
|-- src/
|   |-- config/
|   |-- injector/
|   `-- view/
|-- user_files/
|   |-- config.json
|   `-- media/
|-- assets/
|   `-- packaging/
|-- tests/
`-- dist/
```

## Data Storage

Runtime data is stored inside the add-on directory:

- `addons21/AnkiAnimatedBackground/user_files/config.json`
- `addons21/AnkiAnimatedBackground/user_files/media/`

Packaged sample media can also live under:

- `addons21/AnkiAnimatedBackground/user_files/media/Wallpapers_anki/`

## Development

Build a local package with:

```powershell
.\.venv\Scripts\python.exe package.py
```

Deploy to your local Anki add-ons folder with:

```powershell
.\.venv\Scripts\python.exe deploy.py
```

Run the current test suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Notes And Limitations

- Desktop only.
- Large GIFs and videos can affect Anki responsiveness and memory usage.
- Video playback quality depends on Qt multimedia backend support on the host machine.
- Some codec or platform-specific failures may require switching to another file format or re-encoding the source video.

## Output

Packaging produces:

- `dist/AnkiAnimatedBackground_<version>.ankiaddon`

## License

GPL-3.0. See `LICENSE`.
