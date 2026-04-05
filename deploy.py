import argparse
import os
import platform
import shutil

from build_support import get_version, materialize_release_tree


parser = argparse.ArgumentParser(
    description="Deploy or remove the AnkiAnimatedBackground addon for local development."
)
parser.add_argument(
    "-d", "--delete", action="store_true", help="Remove (uninstall) the addon instead of deploying it."
)
args = parser.parse_args()

VERSION = get_version()
USER_HOME = os.path.expanduser("~")
DEPLOY_BUILD_DIR = ".deploy_build"

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
    materialize_release_tree(DEPLOY_BUILD_DIR, version=VERSION, minify=True)
    if os.path.exists(LOCAL_PATH):
        shutil.rmtree(LOCAL_PATH)
    shutil.move(DEPLOY_BUILD_DIR, LOCAL_PATH)

    print(f"Deployed files to {LOCAL_PATH}")
    print(f"Wrote manifest.json with version: {VERSION}")
