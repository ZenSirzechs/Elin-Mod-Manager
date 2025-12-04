# Elin Mod Manager

A simple mod manager for Elin that simplifies managing mods.

## Installation

1.  Download the latest release (`.exe` file) from the "Releases" section.
2.  Place the `.exe` file in a directory of your choice.

## Usage

1.  Run the `ElinModManager.exe`.
2.  The application will automatically scan the `Mods` folder (located in the same directory as the .exe) for available mods.
3.  Mods are displayed in two lists: "Load Order (Active)" and "Available Storage."
    *   **Load Order (Active):**  Mods in this list are considered installed and active in the game, in the order shown.
    *   **Available Storage:**  Mods in this list are available but not installed/active.
4.  **To install/uninstall mods:** Drag and drop mods between the two lists.  Dragging a mod from "Available Storage" to "Load Order" installs/activates it.  Dragging a mod from "Load Order" to "Available Storage" uninstalls/deactivates it.
5.  **To change load order:** Drag and drop mods within the "Load Order (Active)" list.
6.  **To enable/disable mods within the load order:** Check or uncheck the checkbox next to the mod in the "Load Order (Active)" list.
7.  Click "Apply Load Order" to save changes and create/modify the required symbolic links in the `Package` directory.
8.  Use the search bar to filter the mod lists by title, author, or ID.
9.  Click the refresh button to scan the mod folder again.

*TL;DR: Just put your mods in `Mods` folder and drag and drop.*

## Features

* [x] Easy mod management via drag & drop
* [x] Activate/deactivate mods
* [x] Install/uninstall mods
* [x] Adjust load order
* [x] Delete mod folders (sent to Recycle Bin)
* [ ] Search & filter by tags
* [ ] Save/restore mod lists (profiles)
* [ ] Launch the game from the mod manager
* [ ] Incomplete mod finder
* [ ] Mod config manager
* [ ] Install mod directly when dropped into the Mod Manager window
* [ ] Mod development companion utility
* [ ] Steam Workshop integration and auto migration (Don't know when I will add this as I don't have a legit copy of the game)

## Folder Structure

The mod manager expects the following folder structure:

```
- Elin Mod Manager.exe (or your script)
- Mods/                <- Place your mod folders here
- Package/           <- Symbolic links will be created here
- loadorder.txt      <- Read by mod manager
```

## Running from Source (Python)

If you prefer to run the mod manager directly from the Python source code:

1.  Ensure you have Python 3.6 or later installed.
2.  Install the required dependencies:

    ```bash
    pip install PyQt6 send2trash
    ```
3.  Save the provided code as a `.py` file (e.g., `ModManager.py`).
4.  Run the script from your terminal:

    ```bash
    python ModManager.py
    ```

Ensure that the required directories ("Mods" and "Package") are present in the same directory as the script.
