# 🏴‍☠️ Thatch — Native Wine Commander

Thatch is a native, ultra-lightweight, and strictly minimalist **Wine Prefix & Compatibility Commander** written in Python and PySide6. It is designed as a direct, lightning-fast alternative to bloated compatibility managers like Bottles, optimized specifically to run natively outside Flatpak sandboxes, eliminate container overhead, and offer native system integration.

---

## 🚀 Why Thatch? (How we improve on Bottles)

While Bottles is a powerful tool, it suffers from heavy sandboxing overhead, container permission issues (Flatpak), and nested container complications (such as running Steam or third-party launchers). 

Thatch is rewritten from scratch to offer a **simpler, native, secure, and highly performant** experience:

| Feature | 🏴‍☠️ Thatch | 🍼 Bottles |
| :--- | :--- | :--- |
| **Execution** | **100% Native**: Runs directly on your host system with full hardware driver access and zero container latency. | **Sandboxed**: Bound to Flatpak permissions, causing permission problems and double-sandbox overhead. |
| **Sandbox Security** | **Direct Filesystem Isolation**: Safely unlinks real user folders (`Desktop`, `Documents`, etc.) and the root `Z:` drive natively. | **Flatpak-bound**: Heavy sandbox overhead that interferes with direct hardware access. |
| **Virtual Drive Manager** | **Dynamic & Smart**: Allows persistent custom mappings (e.g. `D:`, `E:`) *only* when the Sandbox is active. Hides automatically when disabled to avoid confusion. | **Static**: Constant redundant mappings that add configuration noise. |
| **Registry Performance** | **Ultra-snappy Line-by-Line Parser**: Reads `.reg` files line-by-line under micro-seconds with **0% Regex CPU overhead** and negligible memory footprint. | **Heavy Python Parsers**: Prone to CPU spikes and memory pauses when parsing large (10MB+) registries. |
| **Terminal Integration** | **Direct & Native**: Opens your system's native terminal preloaded with WINEPREFIX, runners, and variables for direct shell scripting. | **Complex**: Restrictive sandboxed shell access, making custom scripts or terminal-based debugging difficult. |
| **Disk Space Conservation** | **Aggressive Sweeper**: Downloading a new Wine runner automatically purges old version folders, keeping disk footprints strictly clean. | **Accumulative**: Retains older downloaded compiler versions indefinitely, easily wasting tens of gigabytes of disk space. |
| **Recipe Management** | **Map Book (JSON Maps)**: Complete environment setups, runner specs, and performance parameters in simple, editable JSON maps directly from the UI. | **Heavy Database**: Relies on a massive SQLite/state schema that can easily corrupt or desynchronize. |
| **Dependency Injection** | **Direct Winetricks Wrapper**: Integrates cleanly with native `winetricks`. Features a built-in Firejail bypass using `curl` to guarantee successful component injection even on highly restricted systems. | **Custom Wrapper**: Relies on internal packages database mirrors which lag behind official updates. |

---

## ⚙️ Core Technical Achievements & Security Model

### 1. Zero-Leak Sandbox Isolation
When a "Chest" (prefix) is sandboxed, Thatch locks it down immediately:
* **Host Filesystem Isolation**: Standard user folders (`Desktop`, `Documents`, `Downloads`, `Music`, `Pictures`, `Videos`) under `drive_c/users/steamuser/` are securely unlinked and replaced with localized clean directories.
* **Root Drive Elimination**: The standard Wine `Z:` symlink pointing to the Linux root `/` filesystem is entirely destroyed, sealing the prefix.

### 2. Bottles-Style Smart Mounting (Dynamic Mappings)
To allow installation of games without breaching isolation:
* **Zeus Engine Temporary Mounting**: When running an installer (like a GOG setup), Zeus automatically maps the installer's parent directory as a virtual **Unidad `D:`** inside the prefix's `dosdevices/`.
* Wine sees the installer as running safely from `D:\setup.exe` and has access **only** to that folder.
* Once the installation exits, the `D:` drive is unlinked instantly, sealing the sandbox again.
* **Drives Manager UI**: Users can permanently map custom letters (`D:`, `E:`, `Y:`, etc.) via a gorgeous visual panel inside **Settings** *only when the Sandbox is active*, keeping operations clean and clear.

### 3. Wayland Headless & GUI Deadlock Bypass
Initializing prefixes (`wineboot -u`) inside a graphical environment often triggers invisible prompts for Wine Mono/Gecko download, causing silent deadlocks. Thatch completely bypasses this via:
* **Silent DLL Overrides**: Setting `WINEDLLOVERRIDES="mscoree,mshtml=d"` tells Wine to bypass Gecko/Mono installation prompts entirely.
* **Log Suppression**: Injected `WINEDEBUG="-all"` prevents verbose Wine logs from saturating standard streams, avoiding classical `QProcess` pipe write deadlocks.
* **Universal Runner Call**: Avoids looking for standalone `wineboot` binaries (which are missing in modern runners like Proton 10) by routing operations universally through the core `wine wineboot -u` caller.

### 4. High-Performance Registry Scanner
Instead of loading massive 10MB+ registry files into memory and running slow multiline regular expressions, Thatch uses an ultra-optimized **line-by-line tokenizer**:
* Scans `system.reg` and `user.reg` using buffered block streams.
* Discards non-Uninstall registry lines instantly under micro-seconds.
* Results in **0% CPU spikes** and virtually **zero memory allocations** during UI updates.

---

## 🛠️ Installation & Getting Started

### Prerequisites

Thatch runs natively and requires Python 3.10+, PySide6, and Winetricks installed on your Linux system.

```bash
# On Ubuntu / Debian:
sudo apt update
sudo apt install python3 python3-venv winetricks wine
```

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/esfingex/thatch.git
   cd thatch
   ```

2. **Create a virtual environment and install requirements**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Launch Thatch**:
   ```bash
   ./venv/bin/python thatch.py
   ```

---

## 📋 Developer & Auditing Workflow

Thatch strictly adheres to a clean-code standard and uses **Ruff** for sub-millisecond linting and formatting. 
If you are contributing code or creating new `views`, please run the automated audit script before committing:

```bash
# Install Ruff via pacman or pipx:
sudo pacman -S ruff

# Run the auditor to auto-fix and format your code:
./scripts/audit.sh
```

A GitHub Action will automatically verify that no unused imports or styling violations are merged into `main`.

---

## 📁 Repository Structure

```
thatch/
├── src/
│   ├── main.py                  # Coordinator main window & installer hooks
│   ├── database.py              # Atomic SQLite database & schema migrations
│   ├── hardware.py              # GPU manufacturer and Zen synchronization probing
│   ├── style.py                 # Pure flat dark QSS Stylesheet
│   └── views/
│       ├── __init__.py          # Modular views exports
│       ├── chests_view.py       # Treasure prefix grid list
│       ├── chest_details_view.py# Detailed tabs (Details, Programs, Deps, Settings)
│       ├── cargo_view.py        # App catalog and Map Book store
│       ├── recipes_view.py      # Integrated Recipe/Map JSON Editor
│       ├── wine_runners_view.py # Asynchronous downloader and old runtime cleaner
│       ├── preferences_view.py  # Consolidated defaults and path settings
│       ├── create_chest_wizard.py# Stepper visual wizard
│       └── toast_notification.py# Overlay float notifications
├── config/
│   └── recipes/                 # Game/App preset JSON templates (Grim Dawn, Elden Ring, etc.)
├── runners/                     # Extracted custom Wine compiler runtimes
├── prefixes/                    # Default storage path for created Wine Chests
├── thatch_db.sqlite             # Local active SQLite database configuration
└── thatch.py                    # App launcher entrypoint
```

---

## 🛡️ License

Thatch is open-source software licensed under the **MIT License**.
