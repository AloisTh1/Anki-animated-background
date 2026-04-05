import os
import shutil
import zipfile

BUILD_DIR = "build_pkg"
DIST_DIR = "dist"
from build_support import ASSETS_PACKAGING_DIR, get_version, materialize_release_tree


VERSION = get_version()


def create_anki_addon() -> None:
    print("--- Packaging AnkiAnimatedBackground ---")
    materialize_release_tree(BUILD_DIR, version=VERSION, minify=True)

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
