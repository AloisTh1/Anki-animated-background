# CHANGELOG

<!-- version list -->

## Unreleased

### Bug Fixes

- Move runtime settings and imported media out of add-on `user_files` so future Anki updates do not depend on Anki's Windows-sensitive backup rename.
- Package bundled wallpapers under `assets/default_media` and migrate old `user_files` data on startup.

### Upgrade Notes

- Users already stuck on the previous release may need one manual recovery before this fix can install: close Anki, delete or rename `addons21/files_backup` if it exists, make sure no background media file is open in another app, then retry the update or install the fixed `.ankiaddon`.

## v1.3.1 (2026-04-10)

### Bug Fixes

- **ui**: Trigger release for settings dialog responsiveness and theme polish
  ([`95b2cd2`](https://github.com/AloisTh1/Anki-animated-background/commit/95b2cd2264a424bb9b5009d1ad9fc13c273652b7))

## v1.3.0 (2026-04-05)

### Features

- **videos**: Add mc gameplay
  ([`4ad8f48`](https://github.com/AloisTh1/Anki-animated-background/commit/4ad8f48b0734b1b63aff0d445019a27dfd71efcd))


## v1.2.0 (2026-04-05)


## v1.1.0 (2026-04-05)

### Bug Fixes

- **settings**: Remove stale var
  ([`f0992f6`](https://github.com/AloisTh1/Anki-animated-background/commit/f0992f6a1e339b706e74f9fffdef0f056b6a1591))

- **tests**: Remove stale tests
  ([`120f813`](https://github.com/AloisTh1/Anki-animated-background/commit/120f8138a50be0398b058a0c79bc1ad58ae8f800))

### Features

- **preview**: Remove bounce, fix video selection default issue
  ([`84a0bbe`](https://github.com/AloisTh1/Anki-animated-background/commit/84a0bbe01364086968f1f3810e33cb03cda0b568))


## v1.0.2 (2026-04-05)

### Bug Fixes

- **doc**: Replace mermaid
  ([`18d486d`](https://github.com/AloisTh1/Anki-animated-background/commit/18d486dfa5bf8876d3c4eb7b8eb73c92fb3a181e))

- **preview**: Negative values
  ([`77b74f1`](https://github.com/AloisTh1/Anki-animated-background/commit/77b74f1439c8bdfda203cbeba51ebb01784a6aef))


## v1.0.1 (2026-04-05)

### Bug Fixes

- **doc**: Fix doc
  ([`5e5dd6e`](https://github.com/AloisTh1/Anki-animated-background/commit/5e5dd6e42b4dd16f3c0fa2ec9e6d92a93bef4641))

### Documentation

- Clarify architecture diagram
  ([`83780a2`](https://github.com/AloisTh1/Anki-animated-background/commit/83780a2b375a2b36bf97459372c381a8a50032a6))


## v1.0.0 (2026-04-05)

- Initial Release

## v1.0.0 (2026-04-05)

- Rebuilt the project as AnkiAnimatedBackground.
- Removed the legacy predecessor architecture and business logic.
- Added animated webview background injection with four built-in presets.
- Added a settings dialog and JSON-backed configuration.
