import argparse
import json
import os
import platform
import re
import shutil

PYPROJECT_FILENAME = "pyproject.toml"


parser = argparse.ArgumentParser(
    description="Deploy or remove the AnkiAnimatedBackground addon for local development."
)
parser.add_argument(
    "-d", "--delete", action="store_true", help="Remove (uninstall) the addon instead of deploying it."
)
args = parser.parse_args()


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
USER_HOME = os.path.expanduser("~")

if platform.system() == "Windows":
    LOCAL_PATH = os.path.join(
        USER_HOME,
        "AppData",
        "Roaming",
        "Anki2",
        "addons21",
        "AnkiAnimatedBackground",
    )
else:
    LOCAL_PATH = os.path.join(
        USER_HOME,
        ".local",
        "share",
        "Anki2",
        "addons21",
        "AnkiAnimatedBackground",
    )


if args.delete:
    if os.path.exists(LOCAL_PATH):
        print(f"Removing addon from {LOCAL_PATH}...")
        try:
            shutil.rmtree(LOCAL_PATH)
            print("Addon successfully removed.")
        except OSError as error:
            print(f"Error removing addon: {error}")
    else:
        print(f"Addon not found at {LOCAL_PATH}. Nothing to remove.")
else:
    source_dir = "src"
    files_to_copy = ["__init__.py", "README.md", "LICENSE"]
    packaged_media_source = os.path.join("user_files", "media", "Wallpapers_anki")
    packaged_media_target = os.path.join(LOCAL_PATH, "user_files", "media", "Wallpapers_anki")

    os.makedirs(LOCAL_PATH, exist_ok=True)

    target_src_path = os.path.join(LOCAL_PATH, "src")
    if os.path.exists(target_src_path):
        shutil.rmtree(target_src_path)
    shutil.copytree(source_dir, target_src_path)

    for filename in files_to_copy:
        shutil.copy(filename, LOCAL_PATH)

    if os.path.exists(packaged_media_source):
        os.makedirs(os.path.dirname(packaged_media_target), exist_ok=True)
        if os.path.exists(packaged_media_target):
            print(f"Packaged media already exists at {packaged_media_target}; leaving it in place.")
        else:
            shutil.copytree(packaged_media_source, packaged_media_target)

    manifest = {
        "name": "AnkiAnimatedBackground",
        "author": "Alois Thibert",
        "authorUrl": "https://github.com/AloisTh1/Anki-animated-background",
        "package": "AnkiAnimatedBackground",
        "version": VERSION,
        "isDesktopOnly": True,
    }
    with open(os.path.join(LOCAL_PATH, "manifest.json"), "w", encoding="utf-8") as manifest_file:
        json.dump(manifest, manifest_file, indent=4)

    print(f"Deployed files to {LOCAL_PATH}")
    if os.path.exists(packaged_media_target):
        print(f"Included packaged media at {packaged_media_target}")
    print(f"Wrote manifest.json with version: {VERSION}")
