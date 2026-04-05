from __future__ import annotations

import json
import os
import re
import shutil

import python_minifier

SRC_DIR = "src"
ROOT_INIT = "__init__.py"
ASSETS_PACKAGING_DIR = os.path.join("assets", "packaging")
DEFAULT_LOGO_FILENAME = "logo_normal.png"
TARGET_LOGO_PATH_IN_SRC = os.path.join(SRC_DIR, "view", "assets", "logo.png")
PYPROJECT_FILENAME = "pyproject.toml"
UTILS_FILE_PATH_IN_SRC = os.path.join(SRC_DIR, "common", "utils.py")
FILES_TO_INCLUDE_IN_ROOT = ["LICENSE", "README.md"]
USER_FILES_DIR = "user_files"
MANIFEST = {
    "name": "AnkiAnimatedBackground",
    "author": "Alois Thibert",
    "description": "Inject animated backgrounds into Anki webviews.",
    "isDesktopOnly": True,
    "authorUrl": "https://github.com/AloisTh1/Anki-animated-background",
    "package": "AnkiAnimatedBackground",
    "min_anki_version": "24.06.0",
}


def get_version() -> str:
    version_pattern = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']\s*$')
    in_project_section = False

    with open(PYPROJECT_FILENAME, "r", encoding="utf-8") as file_handle:
        for raw_line in file_handle:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("[") and stripped.endswith("]"):
                in_project_section = stripped == "[project]"
                continue

            if not in_project_section:
                continue

            if match := version_pattern.match(stripped):
                return match.group(1).strip()

    raise RuntimeError("Could not read [project].version from pyproject.toml.")


def create_manifest(version: str) -> dict[str, str | bool]:
    manifest = dict(MANIFEST)
    manifest["version"] = version
    return manifest


def minify_code_in_directory(directory: str) -> None:
    print("Minifying Python files...")
    for root, _, files in os.walk(directory):
        for filename in files:
            if not filename.endswith(".py"):
                continue

            file_path = os.path.join(root, filename)
            try:
                with open(file_path, "r+", encoding="utf-8") as file_handle:
                    source = file_handle.read()
                    minified = python_minifier.minify(
                        source,
                        remove_literal_statements=True,
                    )
                    file_handle.seek(0)
                    file_handle.write(minified)
                    file_handle.truncate()
            except Exception as error:
                print(f"Could not minify {file_path}: {error}")


def materialize_release_tree(target_dir: str, *, version: str, minify: bool) -> None:
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir)

    print("Copying source files...")
    shutil.copytree(
        SRC_DIR,
        os.path.join(target_dir, SRC_DIR),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copy(ROOT_INIT, target_dir)

    if os.path.isdir(USER_FILES_DIR):
        print("Including packaged user files...")
        shutil.copytree(
            USER_FILES_DIR,
            os.path.join(target_dir, USER_FILES_DIR),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )

    print("Including documentation files...")
    for filename in FILES_TO_INCLUDE_IN_ROOT:
        target_path = os.path.join(target_dir, filename)
        if os.path.exists(filename):
            shutil.copy(filename, target_path)
        else:
            print(f"WARNING: Documentation file '{filename}' not found. Skipping.")

    source_logo = os.path.join(ASSETS_PACKAGING_DIR, DEFAULT_LOGO_FILENAME)
    target_logo = os.path.join(target_dir, TARGET_LOGO_PATH_IN_SRC)
    if os.path.exists(source_logo):
        print(f"Applying logo: {DEFAULT_LOGO_FILENAME}")
        os.makedirs(os.path.dirname(target_logo), exist_ok=True)
        shutil.copy(source_logo, target_logo)
    else:
        print(f"WARNING: Default logo not found at '{source_logo}'.")

    print("Disabling debug logging for release...")
    utils_path_in_target = os.path.join(target_dir, UTILS_FILE_PATH_IN_SRC)
    try:
        with open(utils_path_in_target, "r+", encoding="utf-8") as file_handle:
            content = file_handle.read()
            file_handle.seek(0)
            file_handle.truncate()
            file_handle.write(content.replace("LOGGING_ON = 1", "LOGGING_ON = 0"))
    except FileNotFoundError:
        print(f"WARNING: Could not find utils.py at {utils_path_in_target} to disable logging.")

    if minify:
        minify_code_in_directory(target_dir)

    print("Generating manifest.json...")
    manifest_path = os.path.join(target_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as file_handle:
        json.dump(create_manifest(version), file_handle, indent=4)
