"""VS Code integration helpers."""

import os
import subprocess

from nicegui import ui


def open_directory(path: str):
    """Open a directory or file in VS Code."""
    try:
        subprocess.Popen(["code", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        try:
            subprocess.Popen(
                ["open", "-a", "Visual Studio Code", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            ui.notify("Could not open VS Code", type="warning")


def open_file(project_dir: str, file_path: str):
    """Open a specific file in an existing VS Code window."""
    full_path = os.path.join(project_dir, file_path)
    try:
        subprocess.Popen(
            ["code", "--goto", full_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        try:
            subprocess.Popen(
                ["open", "-a", "Visual Studio Code", full_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            ui.notify("Could not open VS Code", type="warning")
