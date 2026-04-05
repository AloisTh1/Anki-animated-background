import json
import os
import re
import shutil
import zipfile

import python_minifier

SRC_DIR = "src"
ROOT_INIT = "__init__.py"
ASSETS_PACKAGING_DIR = os.path.join("assets", "packaging")
DEFAULT_LOGO_FILENAME = "logo_normal.png"
TARGET_LOGO_PATH_IN_SRC = os.path.join(SRC_DIR, "view", "assets", "logo.png")
PYPROJECT_FILENAME = "pyproject.toml"
UTILS_FILE_PATH_IN_SRC = os.path.join(SRC_DIR, "common", "utils.py")
BUILD_DIR = "build_pkg"
DIST_DIR = "dist"
FILES_TO_INCLUDE_IN_ROOT = ["LICENSE", "README.md"]
USER_FILES_DIR = "user_files"


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


VERSION = get_version()


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


def create_anki_addon() -> None:
    print("--- Packaging AnkiAnimatedBackground ---")

    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)

    print("Copying source files...")
    shutil.copytree(
        SRC_DIR,
        os.path.join(BUILD_DIR, SRC_DIR),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copy(ROOT_INIT, BUILD_DIR)
    if os.path.isdir(USER_FILES_DIR):
        print("Including packaged user media...")
        shutil.copytree(
            USER_FILES_DIR,
            os.path.join(BUILD_DIR, USER_FILES_DIR),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )

    print("Including documentation files...")
    for filename in FILES_TO_INCLUDE_IN_ROOT:
        target_path = os.path.join(BUILD_DIR, filename)
        if os.path.exists(filename):
            shutil.copy(filename, target_path)
        else:
            print(f"WARNING: Documentation file '{filename}' not found. Skipping.")

    source_logo = os.path.join(ASSETS_PACKAGING_DIR, DEFAULT_LOGO_FILENAME)
    target_logo = os.path.join(BUILD_DIR, TARGET_LOGO_PATH_IN_SRC)
    if os.path.exists(source_logo):
        print(f"Applying logo: {DEFAULT_LOGO_FILENAME}")
        os.makedirs(os.path.dirname(target_logo), exist_ok=True)
        shutil.copy(source_logo, target_logo)
    else:
        print(f"WARNING: Default logo not found at '{source_logo}'.")

    print("Disabling debug logging for release...")
    utils_path_in_build = os.path.join(BUILD_DIR, UTILS_FILE_PATH_IN_SRC)
    try:
        with open(utils_path_in_build, "r+", encoding="utf-8") as file_handle:
            content = file_handle.read()
            file_handle.seek(0)
            file_handle.truncate()
            file_handle.write(content.replace("LOGGING_ON = 1", "LOGGING_ON = 0"))
    except FileNotFoundError:
        print(f"WARNING: Could not find utils.py at {utils_path_in_build} to disable logging.")

    minify_code_in_directory(BUILD_DIR)

    print("Generating manifest.json...")
    manifest = {
        "name": "AnkiAnimatedBackground",
        "author": "Alois Thibert",
        "description": "Inject animated backgrounds into Anki webviews.",
        "isDesktopOnly": True,
        "authorUrl": "https://github.com/AloisTh1/Anki-animated-background",
        "package": "AnkiAnimatedBackground",
        "version": VERSION,
        "min_anki_version": "24.06.0",
    }
    manifest_path = os.path.join(BUILD_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as file_handle:
        json.dump(manifest, file_handle, indent=4)

    output_filename_base = f"AnkiAnimatedBackground_{VERSION}"
    output_zip_path = os.path.join(DIST_DIR, f"{output_filename_base}.zip")
    output_addon_path = os.path.join(DIST_DIR, f"{output_filename_base}.ankiaddon")

    print(f"Creating archive: {output_addon_path}")
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_handle:
        for root, dirs, files in os.walk(BUILD_DIR):
            dirs[:] = [directory for directory in dirs if directory != "__pycache__"]
            for filename in files:
                if filename.endswith((".pyc", ".pyo", ".DS_Store")):
                    continue
                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, BUILD_DIR)
                zip_handle.write(file_path, arcname)

    if os.path.exists(output_addon_path):
        os.remove(output_addon_path)
    os.rename(output_zip_path, output_addon_path)

    print("Cleaning up build directory...")
    shutil.rmtree(BUILD_DIR)
    print(f"Successfully packaged {output_addon_path}\n")


def main() -> None:
    if not os.path.exists(DIST_DIR):
        os.makedirs(DIST_DIR)
    if not os.path.isdir(ASSETS_PACKAGING_DIR):
        print(f"ERROR: Packaging assets directory not found at '{ASSETS_PACKAGING_DIR}'")
        print("Please create it and add packaging assets (default logo).")
        return

    create_anki_addon()
    print("Package created successfully.")
    print(f"Find the .ankiaddon file in the '{DIST_DIR}/' directory.")


if __name__ == "__main__":
    main()
