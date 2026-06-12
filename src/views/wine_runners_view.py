from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QMessageBox,
)
from PySide6.QtCore import Slot, Qt, QThread, Signal
from pathlib import Path
import urllib.request
import tarfile
import shutil
from database import ThatchDB


class IndexLoaderWorker(QThread):
    """
    Asynchronous background thread for loading and parsing the Bottles index.yml.
    """

    loaded = Signal(list)
    error = Signal(str)

    def run(self) -> None:
        try:
            url = "https://raw.githubusercontent.com/bottlesdevs/components/main/index.yml"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                },
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode("utf-8")

            # Simple native YAML parser
            data = {}
            current_key = None
            for raw_line in content.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    parts = line.split(":", 1)
                    k = parts[0].strip()
                    v = parts[1].strip()
                    if not raw_line.startswith(" ") and not raw_line.startswith("\t"):
                        current_key = k
                        data[current_key] = {}
                    else:
                        if current_key:
                            data[current_key][k] = v

            # Build and group runners list by category to keep only the latest stable version
            grouped = {}
            for name, info in data.items():
                category = info.get("Category", "").strip()
                sub_category = info.get("Sub-category", "").strip()
                if category == "runners" and sub_category == "wine":
                    name_lower = name.lower()
                    if "soda" in name_lower:
                        group_key = "Soda"
                    elif "caffe" in name_lower:
                        group_key = "Caffe"
                    elif "ge-proton" in name_lower or "wine-ge" in name_lower:
                        group_key = "Wine-GE"
                    else:
                        group_key = name.split("-")[0].title()

                    date_val = info.get("Date", "0")
                    if group_key not in grouped:
                        grouped[group_key] = []
                    grouped[group_key].append(
                        {"id": name, "name": name, "date": date_val, "info": info}
                    )

            # Keep only the latest for each category group
            runners_list = []
            for group_key, items in grouped.items():
                items.sort(key=lambda x: x["date"], reverse=True)
                latest_item = items[0]
                name = latest_item["name"]

                desc = f"Official Bottles {name} engine."
                if group_key == "Soda":
                    desc = f"Official Bottles latest Soda {name} runner with dynamic Fsync/Esync gaming support."
                elif group_key == "Caffe":
                    desc = f"Official Bottles latest Caffe {name} general-purpose compatibility runner."
                elif group_key == "Wine-GE":
                    desc = f"GloriousEggroll's latest custom {name} runner optimized for high-end gaming."

                runners_list.append(
                    {
                        "id": name,
                        "name": f"{group_key} (Latest: {name})",
                        "desc": desc,
                        "date": latest_item["date"],
                        "category_group": group_key,
                    }
                )

            # Fetch latest custom GE-Proton release dynamically from Github releases!
            try:
                ge_api = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
                ge_req = urllib.request.Request(
                    ge_api, headers={"User-Agent": "Mozilla/5.0"}
                )
                import json

                with urllib.request.urlopen(ge_req, timeout=5) as ge_res:
                    ge_data = json.loads(ge_res.read().decode("utf-8"))
                    ge_tag = ge_data.get("tag_name", "")
                    if ge_tag:
                        ge_url = ""
                        for asset in ge_data.get("assets", []):
                            asset_name = asset.get("name", "")
                            if asset_name.endswith(
                                ".tar.gz"
                            ) and not asset_name.endswith(".sha512sum"):
                                ge_url = asset.get("browser_download_url", "")
                                break
                        if ge_url:
                            runners_list.append(
                                {
                                    "id": f"ge-proton-custom-{ge_tag}",
                                    "name": f"GE-Proton (Latest: {ge_tag})",
                                    "desc": f"GloriousEggroll's latest custom {ge_tag} Steam Proton engine optimized for maximum compatibility.",
                                    "date": ge_data.get("published_at", "2026-05-29"),
                                    "category_group": "GE-Proton",
                                    "custom_download_url": ge_url,
                                }
                            )
            except Exception as ge_err:
                print(f"Error fetching latest GE-Proton: {ge_err}")

            # Sort categories alphabetically
            runners_list.sort(key=lambda r: r["category_group"])
            self.loaded.emit(runners_list)
        except Exception as e:
            self.error.emit(str(e))


class RunnerDownloadWorker(QThread):
    """
    Asynchronous background thread for downloading and extracting Wine runners.
    Queries the individual YAML manifest from Bottles to resolve download links.
    """

    progress = Signal(int)
    status = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self, name: str, dest_dir: Path, custom_url: str | None = None
    ) -> None:
        super().__init__()
        self.name = name
        self.dest_dir = dest_dir
        self.custom_url = custom_url

    def run(self) -> None:
        try:
            download_url = ""
            if self.custom_url:
                download_url = self.custom_url
                self.status.emit("Preparando descarga de GE-Proton...")
            else:
                self.status.emit(f"Consultando manifiesto del runner {self.name}...")

                # Fetch the manifest YAML
                manifest_url = f"https://raw.githubusercontent.com/bottlesdevs/components/main/runners/wine/{self.name}.yml"
                req = urllib.request.Request(
                    manifest_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    manifest_content = response.read().decode("utf-8")

                # Parse YAML manifest to extract URL
                for raw_line in manifest_content.splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line:
                        parts = line.split(":", 1)
                        k = parts[0].strip()
                        v = parts[1].strip()
                        if k == "url":
                            download_url = v

                # Fallbacks in case manifest parsing is blocked
                if not download_url:
                    if "soda" in self.name.lower() or "caffe" in self.name.lower():
                        download_url = f"https://github.com/bottlesdevs/wine/releases/download/{self.name}/{self.name}-x86_64.tar.xz"
                    elif (
                        "wine-ge" in self.name.lower()
                        or "ge-proton" in self.name.lower()
                    ):
                        tag_name = self.name.replace(
                            "wine-ge-proton", "GE-Proton"
                        ).replace("wine-ge-", "GE-Proton")
                        download_url = f"https://github.com/GloriousEggroll/wine-ge-custom/releases/download/{tag_name}/wine-lutris-{tag_name}-x86_64.tar.xz"

            if not download_url:
                raise ValueError(
                    "No se pudo resolver la URL de descarga para este runner."
                )

            self.status.emit(f"Conectando para descargar {self.name}...")
            self.dest_dir.mkdir(parents=True, exist_ok=True)

            # Temporary file path
            temp_archive = self.dest_dir / f"temp_{self.name}.tar"
            if temp_archive.exists():
                temp_archive.unlink()

            req = urllib.request.Request(
                download_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                },
            )

            with urllib.request.urlopen(req) as response:
                total_size = int(response.info().get("Content-Length", 0))
                bytes_downloaded = 0
                block_size = 16384

                with open(temp_archive, "wb") as out_file:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        bytes_downloaded += len(buffer)
                        out_file.write(buffer)

                        if total_size > 0:
                            pct = int((bytes_downloaded / total_size) * 90)
                            self.progress.emit(pct)
                            self.status.emit(f"Downloading {self.name}: {pct}%")

            self.status.emit("Extracting Wine runner...")
            self.progress.emit(93)

            try:
                with tarfile.open(temp_archive) as tar:
                    tar.extractall(path=self.dest_dir)
            except Exception as extract_err:
                raise RuntimeError(f"Extraction failed: {extract_err}")
            finally:
                if temp_archive.exists():
                    temp_archive.unlink()

            self.progress.emit(100)
            self.finished.emit(self.name)

        except Exception as e:
            self.error.emit(str(e))


class WineRunnersView(QWidget):
    """
    Dedicated view for managing and downloading customized compiler engines.
    Fetches the official Bottles index dynamically and handles installations.
    """

    runner_downloaded = Signal(str)
    toast_requested = Signal(str)

    def __init__(
        self, db: ThatchDB, runners: list[str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.runners = runners
        self.download_worker = None
        self.active_download_folder = ""
        self.available_runners = []

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # 1. Header Layout
        lbl_title = QLabel("Wine Runners")
        lbl_title.setObjectName("ViewTitle")
        layout.addWidget(lbl_title)

        # 2. Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }"
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(16)

        # Main Container Card
        card_runners = QFrame()
        card_runners.setObjectName("PrefCard")
        run_layout = QVBoxLayout(card_runners)
        run_layout.setSpacing(12)

        lbl_run_title = QLabel("Wine Runners Downloader")
        lbl_run_title.setObjectName("CardTitle")
        run_layout.addWidget(lbl_run_title)

        lbl_run_desc = QLabel(
            "Descarga runtimes y runners de compilación personalizados de forma asíncrona.\n"
            "Nota: Para optimizar espacio, instalar un runner elimina versiones antiguas de ese mismo tipo."
        )
        lbl_run_desc.setStyleSheet(
            "color: #71717a; font-size: 12px; line-height: 18px; margin-bottom: 4px;"
        )
        run_layout.addWidget(lbl_run_desc)

        # Active download display row (hidden initially)
        self.down_status_frame = QFrame()
        self.down_status_frame.setStyleSheet(
            "background-color: #121214; border: 1px solid #2d2d34; border-radius: 6px; padding: 10px;"
        )
        status_box = QVBoxLayout(self.down_status_frame)
        status_box.setSpacing(6)

        self.lbl_download_status = QLabel("Ready")
        self.lbl_download_status.setStyleSheet(
            "color: #ffffff; font-size: 11px; font-weight: bold;"
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        status_box.addWidget(self.lbl_download_status)
        status_box.addWidget(self.progress_bar)
        run_layout.addWidget(self.down_status_frame)
        self.down_status_frame.hide()

        # Runners rows container
        self.runners_list_widget = QWidget()
        self.runners_list_widget.setStyleSheet("background-color: transparent;")
        self.runners_rows_layout = QVBoxLayout(self.runners_list_widget)
        self.runners_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.runners_rows_layout.setSpacing(8)

        run_layout.addWidget(self.runners_list_widget)
        scroll_layout.addWidget(card_runners)
        scroll_layout.addStretch(1)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        # Initial scan load of local folders
        self._refresh_runners_list()

        # Load index.yml in background
        self.lbl_download_status.setText("Cargando catálogo oficial de Bottles...")
        self.down_status_frame.show()
        self.index_loader = IndexLoaderWorker()
        self.index_loader.loaded.connect(self._on_index_loaded)
        self.index_loader.error.connect(self._on_index_error)
        self.index_loader.start()

    def update_runners_list(self, runners: list[str]) -> None:
        """Externally updates the list of installed wine runners."""
        self.runners = runners
        self._refresh_runners_list()

    def _on_index_loaded(self, runners_list: list) -> None:
        self.available_runners = runners_list
        self.down_status_frame.hide()
        self._refresh_runners_list()

    def _on_index_error(self, err_msg: str) -> None:
        self.down_status_frame.hide()
        # Fallback to local stable defaults in case of network issue
        self.available_runners = [
            {
                "id": "soda-9.0-1",
                "name": "soda-9.0-1",
                "desc": "Bottles Soda 9.0-1 runner with dynamic Fsync/Esync gaming support (local fallback).",
            },
            {
                "id": "caffe-9.7",
                "name": "caffe-9.7",
                "desc": "Bottles Caffe 9.7 general-purpose compatibility runner (local fallback).",
            },
        ]
        self._refresh_runners_list()
        print(f"[WineRunners index] Failed to load remote catalog: {err_msg}")

    def _refresh_runners_list(self) -> None:
        """Clears and re-renders the visual list of available runners with their installation state."""
        # Clear layout
        while self.runners_rows_layout.count():
            item = self.runners_rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Read folders in runners_dir
        runners_dir = self.db.get_runners_dir()
        installed_folders = []
        if runners_dir.exists():
            installed_folders = [d.name for d in runners_dir.iterdir() if d.is_dir()]

        for runner_data in self.available_runners:
            r_id = runner_data["id"]

            # Map dynamic folder names
            if r_id.startswith("ge-proton-custom-"):
                folder_name = r_id.replace("ge-proton-custom-", "")
            elif "wine-ge" in r_id or "ge-proton" in r_id:
                tag_part = (
                    r_id.replace("wine-ge-", "")
                    .replace("wine-", "")
                    .replace("proton", "Proton")
                )
                folder_name = f"lutris-{tag_part}-x86_64"
            else:
                folder_name = f"{r_id}-x86_64"

            runner_data["folder"] = folder_name

            row = QFrame()
            row.setStyleSheet(
                "background-color: #121214; border: 1px solid #2d2d34; border-radius: 6px; padding: 12px;"
            )
            row_layout = QVBoxLayout(row)
            row_layout.setSpacing(4)

            top_layout = QHBoxLayout()
            lbl_name = QLabel(runner_data["name"])
            lbl_name.setStyleSheet(
                "color: #ffffff; font-weight: bold; font-size: 13px;"
            )

            top_layout.addWidget(lbl_name)
            top_layout.addStretch(1)

            # Check installation state
            is_installed = folder_name in installed_folders

            if is_installed:
                lbl_badge = QLabel("✓ Active")
                lbl_badge.setObjectName("BadgeReady")
                top_layout.addWidget(lbl_badge)

            btn_down = QPushButton("🔄")
            btn_down.setObjectName("BlueBtn")
            btn_down.setCursor(Qt.PointingHandCursor)
            btn_down.setToolTip("Descargar / Actualizar Runner")
            btn_down.setStyleSheet(
                "padding: 4px 8px; font-size: 13px; font-weight: bold;"
            )
            btn_down.clicked.connect(
                lambda checked=False, r=runner_data: self._start_runner_download(r)
            )
            top_layout.addWidget(btn_down)

            row_layout.addLayout(top_layout)

            lbl_desc = QLabel(runner_data["desc"])
            lbl_desc.setStyleSheet("color: #71717a; font-size: 11px;")
            lbl_desc.setWordWrap(True)
            row_layout.addWidget(lbl_desc)

            self.runners_rows_layout.addWidget(row)

    def _start_runner_download(self, runner_data: dict) -> None:
        if self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(
                self,
                "Download in Progress",
                "Another runner download is currently in progress. Please wait.",
            )
            return

        self.down_status_frame.show()
        self.progress_bar.setValue(0)
        self.lbl_download_status.setText(
            f"Initializing download: {runner_data['name']}"
        )

        # Cache active folder to preserve during disk sweep cleanup
        self.active_download_folder = runner_data["folder"]

        # Create asynchronous worker thread
        self.download_worker = RunnerDownloadWorker(
            runner_data["name"],
            self.db.get_runners_dir(),
            custom_url=runner_data.get("custom_download_url"),
        )

        # Hook signals
        self.download_worker.progress.connect(self.progress_bar.setValue)
        self.download_worker.status.connect(self.lbl_download_status.setText)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.error.connect(self._on_download_error)

        # Disable list interactions
        self.runners_list_widget.setEnabled(False)
        self.download_worker.start()

    @Slot(str)
    def _on_download_finished(self, name: str) -> None:
        # Disk Sweeper: Purge ONLY older versions of the SAME runner type!
        runners_dir = self.db.get_runners_dir()
        purged_count = 0

        # Identify the type of the newly downloaded runner
        downloaded_name = self.active_download_folder.lower()
        runner_type = ""
        if downloaded_name.startswith("soda"):
            runner_type = "soda"
        elif downloaded_name.startswith("caffe"):
            runner_type = "caffe"
        elif downloaded_name.startswith("lutris"):
            runner_type = "lutris"

        if runners_dir.exists() and runner_type:
            for item in runners_dir.iterdir():
                if item.is_dir() and item.name != self.active_download_folder:
                    folder_name = item.name.lower()
                    is_same_type = False
                    if runner_type == "soda" and folder_name.startswith("soda"):
                        is_same_type = True
                    elif runner_type == "caffe" and folder_name.startswith("caffe"):
                        is_same_type = True
                    elif runner_type == "lutris" and (
                        folder_name.startswith("lutris")
                        or folder_name.startswith("wine-lutris")
                        or "ge-proton" in folder_name
                    ):
                        is_same_type = True

                    if is_same_type:
                        try:
                            shutil.rmtree(item)
                            purged_count += 1
                        except Exception as clean_err:
                            print(
                                f"[Runners Cleanup] Error purging older runner folder {item.name}: {clean_err}"
                            )

        self.down_status_frame.hide()
        self.runners_list_widget.setEnabled(True)

        # Direct user notifications
        if purged_count > 0:
            self.toast_requested.emit(
                f"¡Runner '{name}' listo! Se purgaron {purged_count} compilaciones antiguas."
            )
        else:
            self.toast_requested.emit(f"¡Runner '{name}' listo e instalado!")

        # Emit signal to notify main stacked windows
        self.runner_downloaded.emit(name)
        self.download_worker = None

    @Slot(str)
    def _on_download_error(self, err_msg: str) -> None:
        self.down_status_frame.hide()
        self.runners_list_widget.setEnabled(True)
        QMessageBox.critical(
            self,
            "Runner Download Error",
            f"Failed to download or extract Wine runner:\n{err_msg}",
        )
        self.download_worker = None
