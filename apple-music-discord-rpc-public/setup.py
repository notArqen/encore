#!/usr/bin/env python3
"""
interactive setup for the Apple Music -> Discord Rich Presence helper.

run this with:

    python3 setup.py

it will:
  1. ask for your Discord Application Client ID (and a couple of optional
     cosmetic settings) and write them into config.py.
  2. install the required Python packages (pypresence, pyobjc-framework-Cocoa).
  3. generate a filled-in launchd .plist (for auto-starting at login) with
     the correct Python interpreter and project paths for THIS machine.
  4. optionally install and load that LaunchAgent for you right now.

no terminal experience is assumed -- every step asks a plain yes/no or
text question and explains what it's about to do before doing it.
"""

import os
import re
import shutil
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.py")
PLIST_TEMPLATE_PATH = os.path.join(PROJECT_DIR, "com.user.applemusicdiscordrpc.plist")
PLIST_LABEL = "com.user.applemusicdiscordrpc"
LAUNCH_AGENTS_DIR = os.path.expanduser("~/Library/LaunchAgents")


def banner(text: str) -> None:
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input(f"{prompt}{suffix}: ").strip()
        if answer:
            return answer
        if default is not None:
            return default
        print("  (this one's required -- please type something)")


def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    default_label = "Y/n" if default_yes else "y/N"
    while True:
        answer = input(f"{prompt} [{default_label}]: ").strip().lower()
        if not answer:
            return default_yes
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  please answer y or n")


def check_macos() -> None:
    if sys.platform != "darwin":
        print("this tool only runs on macOS (it needs apple's native music.app, "
              "AppleScript, and NSWorkspace/NSDistributedNotificationCenter, "
              "none of which exist on other platforms).")
        sys.exit(1)


def step_discord_app() -> None:
    banner("step 1 of 4: Discord Application setup")
    print(
        "before this can work, you need a discord application (this is "
        "free and takes about a minute):\n\n"
        "  1. go to https://discord.com/developers/applications\n"
        "  2. click 'New Application', give it any name you like\n"
        "  3. on the 'General Information' page, copy the 'Application ID'\n"
        "     -- that's the Client ID this setup needs next\n"
        "  4. in the left sidebar go to Rich Presence -> Art Assets, and\n"
        "     upload one image to use as the default album art fallback.\n"
        "     name it 'logo' (or pick your own key and enter\n"
        "     it below).\n"
    )
    input("press enter once you've done that and have your Client ID handy...")


def step_configure(values: dict) -> None:
    banner("step 2 of 4: configuration")

    client_id = ask("Discord Application Client ID (numbers only)")
    while not client_id.isdigit():
        print("  that doesn't look like a numeric Client ID -- check the "
              "Developer Portal's 'General Information' page and try again.")
        client_id = ask("Discord Application Client ID (numbers only)")
    values["client_id"] = client_id

    values["asset_key"] = ask(
        "Art Asset key you uploaded as the fallback image", default="logo"
    )

    values["activity_name"] = ask(
        "What should the 'Listening to ___' header say?", default="Apple Music"
    )


def write_config(values: dict) -> None:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(
        r'DISCORD_CLIENT_ID = ".*?"',
        f'DISCORD_CLIENT_ID = "{values["client_id"]}"',
        content,
    )
    content = re.sub(
        r'FALLBACK_ARTWORK_ASSET_KEY = ".*?"',
        f'FALLBACK_ARTWORK_ASSET_KEY = "{values["asset_key"]}"',
        content,
    )
    content = re.sub(
        r'ACTIVITY_NAME = ".*?"',
        f'ACTIVITY_NAME = "{values["activity_name"]}"',
        content,
    )

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\nWrote settings to {CONFIG_PATH}")


def step_install_dependencies() -> None:
    banner("step 3 of 4: install dependencies")
    packages = ["pypresence", "pyobjc-framework-Cocoa"]
    print(f"about to run: {sys.executable} -m pip install {' '.join(packages)}")
    if not ask_yes_no("proceed with installing these now?", default_yes=True):
        print("skipped. You'll need to install these yourself before running "
              "main.py:")
        print(f"  {sys.executable} -m pip install {' '.join(packages)}")
        return

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *packages])
    except subprocess.CalledProcessError:
        print(
            "\nthat failed. ff you saw an 'externally-managed-environment' "
            "error, try again with:\n"
            f"  {sys.executable} -m pip install --user {' '.join(packages)}"
        )


def generate_plist() -> str:
    with open(PLIST_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    main_py_path = os.path.join(PROJECT_DIR, "main.py")
    content = content.replace("PYTHON_EXECUTABLE_HERE", sys.executable)
    content = content.replace("PROJECT_DIRECTORY_HERE/main.py", main_py_path)
    content = content.replace("PROJECT_DIRECTORY_HERE", PROJECT_DIR)

    generated_path = os.path.join(PROJECT_DIR, f"{PLIST_LABEL}.generated.plist")
    with open(generated_path, "w", encoding="utf-8") as f:
        f.write(content)

    return generated_path


def step_launch_agent() -> None:
    banner("step 4 of 4: start automatically at login (optional)")
    print(
        "this step creates a 'LaunchAgent' so the helper starts quietly in "
        "the background every time you log in, and just waits for "
        "Music.app to open -- you won't need to run anything by hand again."
    )

    generated_path = generate_plist()
    print(f"\ngenerated a filled-in launch file at:\n  {generated_path}")

    if not ask_yes_no(
        "install this now so it starts automatically at login?", default_yes=True
    ):
        print(
            "\nno problem. to install it later, run:\n"
            f"  cp '{generated_path}' ~/Library/LaunchAgents/{PLIST_LABEL}.plist\n"
            f"  launchctl load ~/Library/LaunchAgents/{PLIST_LABEL}.plist"
        )
        return

    dest_path = os.path.join(LAUNCH_AGENTS_DIR, f"{PLIST_LABEL}.plist")
    try:
        os.makedirs(LAUNCH_AGENTS_DIR, exist_ok=True)
        shutil.copyfile(generated_path, dest_path)
        subprocess.check_call(["launchctl", "load", dest_path])
        print(f"\ninstalled and loaded. check it's running with:\n"
              f"  launchctl list | grep {PLIST_LABEL}")
    except PermissionError:
        print(
            f"\ncouldn't write to {LAUNCH_AGENTS_DIR} (permission denied).\n"
            "this sometimes happens if that folder's ownership got changed. Try:\n"
            f"  sudo chown $(whoami) {LAUNCH_AGENTS_DIR}\n"
            "then re-run this setup script, or run the two commands above by hand."
        )
    except subprocess.CalledProcessError as e:
        print(f"\n'launchctl load' failed: {e}\n"
              "you can try loading it manually with the command above.")


def step_test_run() -> None:
    banner("all set")
    print(
        "you're configured. recommended next step: run the helper "
        "manually once to make sure everything's working before trusting "
        "the background LaunchAgent:\n\n"
        f"  {sys.executable} {os.path.join(PROJECT_DIR, 'main.py')}\n\n"
        "open Music.app, play something, and check Discord shows your "
        "presence. ctrl-C to stop the manual run whenever you're satisfied."
    )


def main() -> None:
    check_macos()
    banner("apple Music -> discord Rich Presence: setup")
    print("this will walk you through getting this running. you can stop "
          "at any time with Ctrl-C and re-run this script later.")

    values: dict = {}
    step_discord_app()
    step_configure(values)
    write_config(values)
    step_install_dependencies()
    step_launch_agent()
    step_test_run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nsetup cancelled. re-run `python3 setup.py` whenever you're ready.")
        sys.exit(1)
