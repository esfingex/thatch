from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QFrame,
    QGridLayout,
    QListWidget,
    QScrollArea,
    QComboBox,
    QCheckBox,
    QInputDialog,
    QLineEdit,
    QListWidgetItem,
    QSizePolicy,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Signal, Qt, Slot, QSize
from pathlib import Path


class ProgramRowWidget(QWidget):
    """Row widget for a program in the Installed Programs list.

    States:
    - linked: has an exe in Thatch DB → shows ▶ Ejecutar + Desinstalar
    - detected: found in Wine registry but no exe linked → shows Vincular
    """

    run_clicked = Signal(str)  # game_name
    delete_clicked = Signal(str)  # game_name
    link_clicked = Signal(str, str)  # reg_program_id, install_location

    def __init__(
        self,
        display_name: str,
        linked: bool = True,
        exe_path: str = "",
        reg_id: str = "",
        install_location: str = "",
        version: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background-color: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        # Left: icon badge + name
        icon = "🎮" if linked else "🔍"
        name_text = display_name
        if exe_path:
            name_text += f"  —  {Path(exe_path).name}"
        elif version:
            name_text += f"  —  v{version}"

        self.lbl_game = QLabel(f"{icon}  {name_text}")
        self.lbl_game.setStyleSheet(
            f"color: {'#ffffff' if linked else '#a1a1aa'}; "
            "font-weight: bold; font-size: 13px; background: transparent;"
        )
        layout.addWidget(self.lbl_game)
        layout.addStretch(1)

        if linked:
            # ▶ Ejecutar
            self.btn_run = QPushButton("▶ Ejecutar")
            self.btn_run.setObjectName("OrangeBtn")
            self.btn_run.setCursor(Qt.PointingHandCursor)
            self.btn_run.setStyleSheet(
                "min-height: 22px; max-height: 22px; padding: 0px 12px; font-size: 11px; font-weight: bold;"
            )
            self.btn_run.clicked.connect(lambda: self.run_clicked.emit(display_name))
            layout.addWidget(self.btn_run)

            self.btn_delete = QPushButton("Desinstalar")
            self.btn_delete.setObjectName("RedBtnText")
            self.btn_delete.setCursor(Qt.PointingHandCursor)
            self.btn_delete.setStyleSheet(
                "min-height: 22px; max-height: 22px; padding: 0px 10px; font-size: 11px; font-weight: bold; background-color: transparent;"
            )
            self.btn_delete.clicked.connect(
                lambda: self.delete_clicked.emit(display_name)
            )
            layout.addWidget(self.btn_delete)
        else:
            # Badge: detected
            lbl_badge = QLabel("Detectado")
            lbl_badge.setStyleSheet(
                "background: #1e3a5f; color: #60a5fa; border-radius: 4px; "
                "padding: 2px 8px; font-size: 10px; font-weight: bold;"
            )
            layout.addWidget(lbl_badge)

            self.btn_link = QPushButton("🔗 Vincular")
            self.btn_link.setObjectName("BlueBtn")
            self.btn_link.setCursor(Qt.PointingHandCursor)
            self.btn_link.setStyleSheet(
                "min-height: 22px; max-height: 22px; padding: 0px 12px; font-size: 11px; font-weight: bold;"
            )
            self.btn_link.clicked.connect(
                lambda: self.link_clicked.emit(reg_id, install_location)
            )
            layout.addWidget(self.btn_link)


class ChestDetailsView(QWidget):
    """
    Detailed Chest panel managing information tabs, runner version override,
    installed program listings, and modular dependency injectors.
    """

    back_requested = Signal()
    run_requested = Signal(str)
    browse_requested = Signal(str)
    terminal_requested = Signal(str)
    delete_requested = Signal(str)
    add_program_requested = Signal(str)
    run_program_requested = Signal(str, str)  # prefix_name, game_name
    remove_program_requested = Signal(str, str)  # prefix_name, game_name
    run_installer_requested = Signal(str, str)  # prefix_name, installer_exe_path
    install_dependency_requested = Signal(str, str)  # prefix_name, verb
    remove_dependency_requested = Signal(str, str)  # prefix_name, verb
    runner_changed = Signal(str, str)  # prefix_name, runner_name
    perf_settings_changed = Signal(
        str, bool, bool, bool
    )  # prefix_name, esync, fsync, sandbox
    virtual_desktop_changed = Signal(str, bool, str)  # prefix_name, enabled, resolution
    dpi_scale_changed = Signal(str, int)  # prefix_name, dpi_value (96/120/144/192)
    monitor_changed = Signal(str, str)  # prefix_name, monitor_name
    link_registry_program_requested = Signal(
        str, str, str
    )  # prefix_name, reg_id, install_location

    def __init__(self, active_gpu: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.active_gpu = active_gpu
        self.prefix_name = ""
        self.games_data = {}
        self.recipes_data = {}
        self.installed_verbs = []
        self.available_runners = []
        self.current_recipe_id = "default_gaming"
        self.prefixes_dir = Path()
        self.active_dep_category = "All"
        self.dep_filter_group = []
        self._registry_programs: list[dict] = []
        self._deps_catalog: list[dict] = []  # dynamic winetricks catalog

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # 1. Header Row
        header_layout = QHBoxLayout()

        self.btn_back = QPushButton("← Back")
        self.btn_back.setStyleSheet(
            "background-color: transparent; border: none; color: #a1a1aa; font-weight: bold; font-size: 14px;"
        )
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.btn_back)
        header_layout.addSpacing(10)

        self.lbl_icon = QLabel("🎮")
        self.lbl_icon.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(self.lbl_icon)

        self.lbl_title = QLabel("Chest Name")
        self.lbl_title.setObjectName("ViewTitle")
        header_layout.addWidget(self.lbl_title, stretch=1)

        # Action Buttons (Top-Right)
        self.btn_run = QPushButton("▶ Run")
        self.btn_run.setObjectName("OrangeBtn")
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.clicked.connect(lambda: self.run_requested.emit(self.prefix_name))
        header_layout.addWidget(self.btn_run)

        self.btn_browse = QPushButton("📁 Browse")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.clicked.connect(
            lambda: self.browse_requested.emit(self.prefix_name)
        )
        header_layout.addWidget(self.btn_browse)

        self.btn_terminal = QPushButton("💻 Terminal")
        self.btn_terminal.setCursor(Qt.PointingHandCursor)
        self.btn_terminal.clicked.connect(
            lambda: self.terminal_requested.emit(self.prefix_name)
        )
        header_layout.addWidget(self.btn_terminal)

        self.btn_delete = QPushButton("🗑")
        self.btn_delete.setObjectName("RedBtnText")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.clicked.connect(
            lambda: self.delete_requested.emit(self.prefix_name)
        )
        header_layout.addWidget(self.btn_delete)

        layout.addLayout(header_layout)

        # 2. Flat Navigation Tabs
        tab_layout = QHBoxLayout()
        tab_layout.setSpacing(10)
        tab_layout.setAlignment(Qt.AlignLeft)

        self.tabs_group = []
        self.tab_details = QPushButton("Details")
        self.tab_details.setObjectName("TabBtn")
        self.tab_details.setCheckable(True)
        self.tab_details.setChecked(True)
        self.tab_details.clicked.connect(lambda: self._switch_tab(0))
        tab_layout.addWidget(self.tab_details)
        self.tabs_group.append(self.tab_details)

        self.tab_programs = QPushButton("Programs")
        self.tab_programs.setObjectName("TabBtn")
        self.tab_programs.setCheckable(True)
        self.tab_programs.clicked.connect(lambda: self._switch_tab(1))
        tab_layout.addWidget(self.tab_programs)
        self.tabs_group.append(self.tab_programs)

        self.tab_dependencies = QPushButton("Dependencies")
        self.tab_dependencies.setObjectName("TabBtn")
        self.tab_dependencies.setCheckable(True)
        self.tab_dependencies.clicked.connect(lambda: self._switch_tab(2))
        tab_layout.addWidget(self.tab_dependencies)
        self.tabs_group.append(self.tab_dependencies)

        self.tab_settings = QPushButton("Settings")
        self.tab_settings.setObjectName("TabBtn")
        self.tab_settings.setCheckable(True)
        self.tab_settings.clicked.connect(lambda: self._switch_tab(3))
        tab_layout.addWidget(self.tab_settings)
        self.tabs_group.append(self.tab_settings)

        layout.addLayout(tab_layout)

        # 3. Stacked widget for Tab Contents
        self.tab_stack = QStackedWidget()
        layout.addWidget(self.tab_stack, stretch=1)

        # Build Tab 1: Details
        self.details_pane = self._build_details_tab()
        self.tab_stack.addWidget(self.details_pane)

        # Build Tab 2: Programs
        self.programs_pane = self._build_programs_tab()
        self.tab_stack.addWidget(self.programs_pane)

        # Build Tab 3: Dependencies
        self.dependencies_pane = self._build_dependencies_tab()
        self.tab_stack.addWidget(self.dependencies_pane)

        # Build Tab 4: Settings
        self.settings_pane = self._build_settings_tab()
        self.tab_stack.addWidget(self.settings_pane)

    def _switch_tab(self, index: int) -> None:
        """Manages mutually exclusive checks on tab buttons and changes stacked index."""
        for idx, btn in enumerate(self.tabs_group):
            btn.setChecked(idx == index)
        self.tab_stack.setCurrentIndex(index)

    def _build_details_tab(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("DetailCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Information")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(14)

        # Metadata values
        labels = [
            "Environment:",
            "Runner:",
            "Architecture:",
            "State:",
            "Path:",
            "Hardware GPU:",
        ]
        self.detail_vals = []

        for idx, label_text in enumerate(labels):
            lbl_tag = QLabel(label_text)
            lbl_tag.setObjectName("CardLabel")
            lbl_val = QLabel("-")
            lbl_val.setObjectName("CardValue")
            lbl_val.setTextInteractionFlags(Qt.TextSelectableByMouse)

            grid.addWidget(lbl_tag, idx, 0)
            grid.addWidget(lbl_val, idx, 1)
            self.detail_vals.append(lbl_val)

        layout.addLayout(grid)
        layout.addStretch(1)
        return widget

    def _build_programs_tab(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("DetailCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header Row inside Card
        header = QHBoxLayout()
        title = QLabel("Installed Programs")
        title.setObjectName("CardTitle")
        header.addWidget(title)

        self.btn_add_program = QPushButton("Vincular ejecutable")
        self.btn_add_program.setCursor(Qt.PointingHandCursor)
        self.btn_add_program.clicked.connect(
            lambda: self.add_program_requested.emit(self.prefix_name)
        )

        self.btn_run_installer = QPushButton("💿 Ejecutar Instalador (.exe)")
        self.btn_run_installer.setObjectName("BlueBtn")
        self.btn_run_installer.setCursor(Qt.PointingHandCursor)
        self.btn_run_installer.clicked.connect(self._on_run_installer_clicked)

        header.addWidget(self.btn_add_program)
        header.addWidget(self.btn_run_installer)
        layout.addLayout(header)

        # Programs List widget
        self.list_programs = QListWidget()
        layout.addWidget(self.list_programs, stretch=1)

        return widget

    def _build_dependencies_tab(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("DetailCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header Row inside Card
        header = QHBoxLayout()
        title = QLabel("Chest Dependencies")
        title.setObjectName("CardTitle")
        header.addWidget(title)
        layout.addLayout(header)

        subtitle = QLabel(
            "Windows components instalados en este WINEPREFIX via Winetricks"
        )
        subtitle.setStyleSheet("color: #71717a; font-size: 13px; margin-bottom: 4px;")
        layout.addWidget(subtitle)

        # ── Search box ─────────────────────────────────────────────────────────
        self.dep_search = QLineEdit()
        self.dep_search.setPlaceholderText(
            "🔍  Buscar componente... (e.g. dxvk, vcrun, dotnet)"
        )
        self.dep_search.setStyleSheet(
            "QLineEdit { background: #18181b; border: 1px solid #3f3f46; border-radius: 8px; "
            "color: #ffffff; padding: 8px 14px; font-size: 13px; } "
            "QLineEdit:focus { border-color: #6366f1; }"
        )
        self.dep_search.textChanged.connect(self._populate_dependencies)
        layout.addWidget(self.dep_search)

        # ── Category Filter tab bar ───────────────────────────────────────────────
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)
        filter_layout.setAlignment(Qt.AlignLeft)

        self.dep_filter_group = []
        categories = ["All", "Libraries", "Fonts", "Settings"]
        for cat in categories:
            btn = QPushButton(cat)
            btn.setObjectName("TabBtn")
            btn.setCheckable(True)
            btn.setChecked(cat == "All")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda checked=False, c=cat: self._on_dep_filter_changed(c)
            )
            filter_layout.addWidget(btn)
            self.dep_filter_group.append(btn)

        layout.addLayout(filter_layout)

        # Scroll Area for dependency rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }"
        )

        self.dep_list_widget = QWidget()
        self.dep_list_widget.setStyleSheet("background-color: transparent;")
        self.dep_layout = QVBoxLayout(self.dep_list_widget)
        self.dep_layout.setContentsMargins(0, 8, 0, 0)
        self.dep_layout.setSpacing(12)

        scroll.setWidget(self.dep_list_widget)
        layout.addWidget(scroll, stretch=1)

        return widget

    def _on_dep_filter_changed(self, category_name: str) -> None:
        self.active_dep_category = category_name
        for btn in self.dep_filter_group:
            btn.setChecked(btn.text() == category_name)
        self._populate_dependencies()

    def _build_settings_tab(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("DetailCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        title = QLabel("Chest Settings")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(14)

        lbl_runner = QLabel("Override Runner:")
        lbl_runner.setObjectName("CardLabel")
        self.combo_runner_override = QComboBox()
        self.combo_runner_override.currentTextChanged.connect(self._on_runner_changed)
        grid.addWidget(lbl_runner, 0, 0)
        grid.addWidget(self.combo_runner_override, 0, 1)

        # Direct Performance controls
        lbl_perf = QLabel("Performance Hacks:")
        lbl_perf.setObjectName("CardLabel")
        grid.addWidget(lbl_perf, 1, 0)

        perf_layout = QVBoxLayout()

        self.chk_esync = QCheckBox("Enable Esync (Eventfd Synchronization)")
        self.chk_esync.setChecked(True)
        self.chk_esync.stateChanged.connect(self._on_perf_settings_changed)

        self.lbl_esync_desc = QLabel(
            "Esync reduces Wineserver overhead using eventfd thread synchronization. Ideal for modern multi-threaded games."
        )
        self.lbl_esync_desc.setStyleSheet(
            "color: #71717a; font-size: 11px; margin-left: 20px; margin-bottom: 8px;"
        )
        self.lbl_esync_desc.setWordWrap(True)

        self.chk_fsync = QCheckBox("Enable Fsync (Futex Synchronization)")
        self.chk_fsync.setChecked(True)
        self.chk_fsync.stateChanged.connect(self._on_perf_settings_changed)

        self.lbl_fsync_desc = QLabel(
            "Fsync leverages kernel futexes directly (requires a compatible Linux kernel, like Zen, XanMod, or CachyOS). Offers even higher FPS."
        )
        self.lbl_fsync_desc.setStyleSheet(
            "color: #71717a; font-size: 11px; margin-left: 20px; margin-bottom: 8px;"
        )
        self.lbl_fsync_desc.setWordWrap(True)

        self.chk_sandbox = QCheckBox("Enable Sandbox Isolation (Secure Laboratory)")
        self.chk_sandbox.setChecked(False)
        self.chk_sandbox.setStyleSheet("color: #60a5fa; font-weight: bold;")
        self.chk_sandbox.stateChanged.connect(self._on_perf_settings_changed)

        self.lbl_sandbox_desc = QLabel(
            "Locks down WINEPREFIX folders, unlinks /home directory access, and disables root disk mapping for secure installations."
        )
        self.lbl_sandbox_desc.setStyleSheet(
            "color: #71717a; font-size: 11px; margin-left: 20px;"
        )
        self.lbl_sandbox_desc.setWordWrap(True)

        perf_layout.addWidget(self.chk_esync)
        perf_layout.addWidget(self.lbl_esync_desc)
        perf_layout.addWidget(self.chk_fsync)
        perf_layout.addWidget(self.lbl_fsync_desc)
        perf_layout.addWidget(self.chk_sandbox)
        perf_layout.addWidget(self.lbl_sandbox_desc)

        grid.addLayout(perf_layout, 1, 1)

        layout.addLayout(grid)

        # ── Separator line ──────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(
            "background-color: #2d2d34; max-height: 1px; border: none; margin: 4px 0;"
        )
        layout.addWidget(sep)

        # ── Display & Scaling Section ───────────────────────────────────────────
        lbl_display_section = QLabel("Display & Scaling")
        lbl_display_section.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #ffffff; margin-bottom: 2px;"
        )
        layout.addWidget(lbl_display_section)

        disp_grid = QGridLayout()
        disp_grid.setSpacing(14)

        # ── DPI Scale ──
        lbl_dpi = QLabel("Escalado DPI:")
        lbl_dpi.setObjectName("CardLabel")
        disp_grid.addWidget(lbl_dpi, 0, 0)

        dpi_right = QVBoxLayout()

        dpi_row = QHBoxLayout()
        self.combo_dpi_scale = QComboBox()
        self.combo_dpi_scale.addItems(
            [
                "96 DPI  —  100%  (predeterminado)",
                "120 DPI  —  125%  (recomendado para GOG)",
                "144 DPI  —  150%",
                "192 DPI  —  200%",
            ]
        )
        self.combo_dpi_scale.currentIndexChanged.connect(self._on_dpi_scale_changed)
        dpi_row.addWidget(self.combo_dpi_scale)
        dpi_row.addStretch(1)
        dpi_right.addLayout(dpi_row)

        lbl_dpi_desc = QLabel(
            "Ajusta la escala de la interfaz de Windows dentro de Wine. "
            "Útil para instaladores GOG o aplicaciones que se ven muy pequeñas en pantalla 1080p."
        )
        lbl_dpi_desc.setStyleSheet("color: #71717a; font-size: 11px; margin-top: 2px;")
        lbl_dpi_desc.setWordWrap(True)
        dpi_right.addWidget(lbl_dpi_desc)
        disp_grid.addLayout(dpi_right, 0, 1)

        # ── Virtual Desktop ──
        lbl_vd = QLabel("Escritorio Virtual:")
        lbl_vd.setObjectName("CardLabel")
        disp_grid.addWidget(lbl_vd, 1, 0)

        vd_right = QVBoxLayout()

        self.chk_virtual_desktop = QCheckBox("Forzar escritorio virtual de Wine")
        self.chk_virtual_desktop.stateChanged.connect(self._on_virtual_desktop_toggled)

        self.lbl_vd_desc = QLabel(
            "Crea un canvas aislado a la resolución elegida. El instalador y el juego "
            "corren completamente dentro de ese canvas. Alternativa al escalado DPI."
        )
        self.lbl_vd_desc.setStyleSheet(
            "color: #71717a; font-size: 11px; margin-left: 20px; margin-top: 2px;"
        )
        self.lbl_vd_desc.setWordWrap(True)

        vd_right.addWidget(self.chk_virtual_desktop)
        vd_right.addWidget(self.lbl_vd_desc)

        res_row = QHBoxLayout()
        self.lbl_vd_res = QLabel("Resolución:")
        self.lbl_vd_res.setStyleSheet(
            "color: #a1a1aa; font-size: 12px; margin-left: 20px;"
        )
        self.combo_vd_resolution = QComboBox()
        self.combo_vd_resolution.addItems(
            ["1920x1080", "2560x1440", "3840x2160", "1280x720", "1600x900"]
        )
        self.combo_vd_resolution.setCurrentText("1920x1080")
        self.combo_vd_resolution.currentTextChanged.connect(
            self._on_virtual_desktop_toggled
        )
        self.combo_vd_resolution.setEnabled(False)
        self.lbl_vd_res.setEnabled(False)

        res_row.addWidget(self.lbl_vd_res)
        res_row.addWidget(self.combo_vd_resolution)
        res_row.addStretch(1)
        vd_right.addLayout(res_row)
        disp_grid.addLayout(vd_right, 1, 1)

        # ── Target Monitor ──
        lbl_monitor = QLabel("Pantalla de Lanzamiento:")
        lbl_monitor.setObjectName("CardLabel")
        disp_grid.addWidget(lbl_monitor, 2, 0)

        monitor_right = QVBoxLayout()
        monitor_row = QHBoxLayout()
        self.combo_monitor = QComboBox()
        self.combo_monitor.currentIndexChanged.connect(self._on_monitor_changed)
        monitor_row.addWidget(self.combo_monitor)
        monitor_row.addStretch(1)
        monitor_right.addLayout(monitor_row)

        lbl_monitor_desc = QLabel(
            "Selecciona en qué monitor/pantalla debe abrirse el juego. "
            "Forzará temporalmente el monitor principal al iniciar el juego."
        )
        lbl_monitor_desc.setStyleSheet(
            "color: #71717a; font-size: 11px; margin-top: 2px;"
        )
        lbl_monitor_desc.setWordWrap(True)
        monitor_right.addWidget(lbl_monitor_desc)
        disp_grid.addLayout(monitor_right, 2, 1)

        disp_grid.setRowStretch(0, 0)
        disp_grid.setRowStretch(1, 0)
        disp_grid.setRowStretch(2, 0)

        layout.addLayout(disp_grid)

        # ── Separator for Virtual Drives Mappings ──────────────────────────────
        sep_drives = QFrame()
        sep_drives.setFrameShape(QFrame.HLine)
        sep_drives.setStyleSheet(
            "background-color: #2d2d34; max-height: 1px; border: none; margin: 12px 0;"
        )
        layout.addWidget(sep_drives)

        # ── Drives Manager Layout ──
        lbl_drives_section = QLabel("Unidades Virtuales (Sandbox / Mapeos)")
        lbl_drives_section.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #ffffff; margin-bottom: 2px;"
        )
        layout.addWidget(lbl_drives_section)

        self.lbl_drives_desc = QLabel(
            "Asigna letras de unidad adicionales (como D:, E:, Y:) que apunten a carpetas específicas de tu sistema. "
            "Wine podrá ver e interactuar SOLAMENTE con esas carpetas, manteniendo a salvo todo lo demás en modo sandbox."
        )
        self.lbl_drives_desc.setStyleSheet(
            "color: #71717a; font-size: 11px; margin-bottom: 8px;"
        )
        self.lbl_drives_desc.setWordWrap(True)
        layout.addWidget(self.lbl_drives_desc)

        # Sandbox disabled warning notice widget
        self.lbl_drives_sandbox_disabled = QLabel(
            "🔓 <b>El Aislamiento de Seguridad (Sandbox) está Desactivado.</b><br>"
            "Este contenedor tiene acceso directo y completo a todo tu disco duro a través de la Unidad Z: predeterminada. "
            "Por seguridad, la configuración de mapeos de unidad adicionales está deshabilitada ya que es innecesaria."
        )
        self.lbl_drives_sandbox_disabled.setStyleSheet(
            "background-color: #1a1a1e; border: 1px solid #ff9f0a; border-radius: 6px; "
            "color: #ff9f0a; font-size: 12px; padding: 12px; margin-bottom: 6px;"
        )
        self.lbl_drives_sandbox_disabled.setWordWrap(True)
        self.lbl_drives_sandbox_disabled.setVisible(False)
        layout.addWidget(self.lbl_drives_sandbox_disabled)

        self.drives_container = QFrame()
        self.drives_container.setStyleSheet(
            "background-color: #121214; border: 1px solid #2c2c2e; border-radius: 8px; "
            "padding: 12px; margin-bottom: 4px;"
        )
        self.drives_layout = QVBoxLayout(self.drives_container)
        self.drives_layout.setContentsMargins(8, 8, 8, 8)
        self.drives_layout.setSpacing(10)
        layout.addWidget(self.drives_container)

        drives_btn_row = QHBoxLayout()
        self.btn_add_drive = QPushButton("➕ Agregar Mapeo de Unidad")
        self.btn_add_drive.setCursor(Qt.PointingHandCursor)
        self.btn_add_drive.setStyleSheet("font-weight: bold; max-width: 250px;")
        self.btn_add_drive.clicked.connect(self._on_add_drive_clicked)
        drives_btn_row.addWidget(self.btn_add_drive)
        drives_btn_row.addStretch(1)
        layout.addLayout(drives_btn_row)

        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }"
        )
        scroll.setWidget(widget)
        return scroll

    def update_view(
        self,
        prefix_name: str,
        games: dict,
        recipes: dict,
        installed_verbs: list[str],
        available_runners: list[str],
        prefixes_dir: Path,
        registry_programs: list[dict] | None = None,
        catalog: list[dict] | None = None,
    ) -> None:
        """Populates all details tabs dynamically for the selected Chest."""
        self.prefix_name = prefix_name
        self.games_data = games
        self.recipes_data = recipes
        self.installed_verbs = installed_verbs
        self.available_runners = available_runners
        self.prefixes_dir = prefixes_dir
        self._registry_programs = registry_programs or []
        if catalog:
            self._deps_catalog = catalog

        display_name = prefix_name.replace("_", " ").title()
        self.lbl_title.setText(display_name)

        # 1. Update basic information details
        # Find environment from associated games
        environment = "Custom"
        runner = "Wine (Sistema)"
        self.current_recipe_id = "default_gaming"

        associated_game = None
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                associated_game = ginfo
                break

        if associated_game:
            self.current_recipe_id = associated_game.get("recipe_id", "default_gaming")
            recipe = recipes.get(self.current_recipe_id, {})
            environment = recipe.get("display_name", "Gaming")
            if "Estándar" in environment or "Genérico" in environment:
                environment = "Gaming"
            runner = associated_game.get("runner", runner)

        # Clean displays
        if "Wine del Sistema" in runner:
            runner = "Wine"

        prefix_path = prefixes_dir / prefix_name
        arch = "win64"
        syswow_dir = prefix_path / "drive_c" / "windows" / "syswow64"
        if prefix_path.exists() and not syswow_dir.exists():
            arch = "win32"

        status = "Ready"
        if "dev" in prefix_name.lower() or "test" in prefix_name.lower():
            status = "Stopped"

        # Set icon
        if "gaming" in environment.lower() or associated_game:
            self.lbl_icon.setText("🎮")
        elif (
            "application" in environment.lower()
            or "office" in prefix_name.lower()
            or "work" in prefix_name.lower()
        ):
            self.lbl_icon.setText("💼")
        else:
            self.lbl_icon.setText("⚙️")

        self.detail_vals[0].setText(environment)
        self.detail_vals[1].setText(runner)
        self.detail_vals[2].setText(arch)
        self.detail_vals[3].setText(status)
        self.detail_vals[4].setText(str(prefix_path))
        self.detail_vals[5].setText(self.active_gpu.upper())

        # 2. Populate Installed Programs tab
        self.list_programs.clear()

        # Build set of already-linked game names (lowercase) for dedup
        linked_names_lower: set[str] = set()
        linked_rows: list[tuple[str, dict]] = []
        for gname, ginfo in games.items():
            if ginfo.get("prefix") == prefix_name:
                exe_val = str(ginfo.get("exe", "")).strip().lower()
                if "contenedor de sistema" in exe_val:
                    continue
                linked_names_lower.add(gname.lower())
                linked_rows.append((gname, ginfo))

        # Show linked programs first (already have exe)
        for gname, ginfo in linked_rows:
            item = QListWidgetItem(self.list_programs)
            row_widget = ProgramRowWidget(
                display_name=gname,
                linked=True,
                exe_path=ginfo.get("exe", ""),
            )
            row_widget.run_clicked.connect(
                lambda name: self.run_program_requested.emit(self.prefix_name, name)
            )
            row_widget.delete_clicked.connect(
                lambda name: self.remove_program_requested.emit(self.prefix_name, name)
            )
            item.setSizeHint(QSize(0, 48))
            self.list_programs.addItem(item)
            self.list_programs.setItemWidget(item, row_widget)

        # Show registry-detected programs that are NOT yet linked
        for reg in self._registry_programs:
            reg_name = reg.get("name", "")
            if not reg_name:
                continue
            # Skip if already linked (fuzzy dedup by lowercase name)
            if reg_name.lower() in linked_names_lower:
                continue
            item = QListWidgetItem(self.list_programs)
            row_widget = ProgramRowWidget(
                display_name=reg_name,
                linked=False,
                reg_id=reg.get("id", reg_name),
                install_location=reg.get("install_location", ""),
                version=reg.get("version", ""),
            )
            row_widget.link_clicked.connect(
                lambda rid, iloc: self.link_registry_program_requested.emit(
                    self.prefix_name, rid, iloc
                )
            )
            item.setSizeHint(QSize(0, 48))
            self.list_programs.addItem(item)
            self.list_programs.setItemWidget(item, row_widget)

        # Empty state
        if self.list_programs.count() == 0:
            item = QListWidgetItem(self.list_programs)
            lbl_empty = QLabel(
                "Ningún programa instalado detectado.\nUsa ‘💿 Ejecutar Instalador’ para instalar un juego."
            )
            lbl_empty.setStyleSheet(
                "color: #52525b; font-size: 12px; font-style: italic; padding: 24px;"
            )
            lbl_empty.setAlignment(Qt.AlignCenter)
            item.setSizeHint(QSize(0, 90))
            self.list_programs.addItem(item)
            self.list_programs.setItemWidget(item, lbl_empty)

        # 3. Populate Dependencies list rows
        self._populate_dependencies()

        # 4. Populate Settings tab
        self.combo_runner_override.blockSignals(True)
        self.combo_runner_override.clear()
        if available_runners:
            self.combo_runner_override.addItems(available_runners)
        self.combo_runner_override.addItem("Wine del Sistema (/usr/bin/wine)")

        # Set current runner index
        idx = self.combo_runner_override.findText(
            associated_game.get("runner", "") if associated_game else ""
        )
        if idx != -1:
            self.combo_runner_override.setCurrentIndex(idx)
        else:
            self.combo_runner_override.setCurrentIndex(
                self.combo_runner_override.count() - 1
            )
        self.combo_runner_override.blockSignals(False)

        # Load Esync/Fsync status from recipe
        recipe = recipes.get(self.current_recipe_id, {})
        perf_env = recipe.get("performance_env", {})
        esync_val = perf_env.get("WINEESYNC", "0") == "1"
        fsync_val = perf_env.get("WINEMFSYNC", "0") == "1"
        sandbox_val = (
            bool(associated_game.get("sandbox", False)) if associated_game else False
        )

        self.chk_esync.blockSignals(True)
        self.chk_fsync.blockSignals(True)
        self.chk_sandbox.blockSignals(True)
        self.chk_esync.setChecked(esync_val)
        self.chk_fsync.setChecked(fsync_val)
        self.chk_sandbox.setChecked(sandbox_val)
        self.chk_esync.blockSignals(False)
        self.chk_fsync.blockSignals(False)
        self.chk_sandbox.blockSignals(False)

        # Load Virtual Desktop settings from associated game record
        vd_enabled = False
        vd_resolution = "1920x1080"
        if associated_game:
            vd_enabled = bool(associated_game.get("virtual_desktop", False))
            vd_resolution = associated_game.get("virtual_desktop_res", "1920x1080")

        self.chk_virtual_desktop.blockSignals(True)
        self.combo_vd_resolution.blockSignals(True)
        self.chk_virtual_desktop.setChecked(vd_enabled)
        self.combo_vd_resolution.setCurrentText(vd_resolution)
        self.combo_vd_resolution.setEnabled(vd_enabled)
        self.lbl_vd_res.setEnabled(vd_enabled)
        self.chk_virtual_desktop.blockSignals(False)
        self.combo_vd_resolution.blockSignals(False)

        # Load DPI scale setting from game record
        dpi_val = 96
        if associated_game:
            dpi_val = int(associated_game.get("dpi_scale", 96))
        dpi_map = {96: 0, 120: 1, 144: 2, 192: 3}
        self.combo_dpi_scale.blockSignals(True)
        self.combo_dpi_scale.setCurrentIndex(dpi_map.get(dpi_val, 0))
        self.combo_dpi_scale.blockSignals(False)

        # Load monitor override from associated game record
        self.combo_monitor.blockSignals(True)
        self.combo_monitor.clear()
        self.combo_monitor.addItem("Por defecto (Principal de X11)", "default")

        # Get dynamic screens using xrandr
        import subprocess

        connected_monitors = []
        try:
            res = subprocess.run(
                ["xrandr", "--query"], capture_output=True, text=True, timeout=2
            )
            for line in res.stdout.splitlines():
                if " connected" in line:
                    parts = line.split()
                    if parts:
                        connected_monitors.append(parts[0])
        except Exception:
            pass

        for mon in connected_monitors:
            self.combo_monitor.addItem(f"Pantalla: {mon}", mon)

        # Select current monitor
        cur_monitor = (
            associated_game.get("target_monitor", "default")
            if associated_game
            else "default"
        )
        found_idx = 0
        for i in range(self.combo_monitor.count()):
            if self.combo_monitor.itemData(i) == cur_monitor:
                found_idx = i
                break
        self.combo_monitor.setCurrentIndex(found_idx)
        self.combo_monitor.blockSignals(False)

        # Load and refresh virtual drives list dynamically based on Sandbox isolation state
        if sandbox_val:
            self.lbl_drives_desc.setVisible(True)
            self.drives_container.setVisible(True)
            self.btn_add_drive.setVisible(True)
            self.lbl_drives_sandbox_disabled.setVisible(False)
            self.update_drives_list()
        else:
            self.lbl_drives_desc.setVisible(False)
            self.drives_container.setVisible(False)
            self.btn_add_drive.setVisible(False)
            self.lbl_drives_sandbox_disabled.setVisible(True)

    def _populate_dependencies(self) -> None:
        """Clears and renders dependency rows filtered by category and search query."""
        # Clear existing row widgets
        while self.dep_layout.count():
            item = self.dep_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Use the dynamic catalog if available, otherwise empty list
        deps_source = self._deps_catalog if self._deps_catalog else []

        # Apply category + search filters
        search_query = (
            self.dep_search.text().strip().lower()
            if hasattr(self, "dep_search")
            else ""
        )

        filtered = [
            dep
            for dep in deps_source
            if (
                self.active_dep_category == "All"
                or dep["type"] == self.active_dep_category
            )
            and (
                not search_query
                or search_query in dep["verb"].lower()
                or search_query in dep["name"].lower()
                or search_query in dep.get("desc", "").lower()
            )
        ]

        if not filtered:
            # Show empty placeholder label with custom status depending on winetricks presence
            import shutil

            if not shutil.which("winetricks"):
                msg = "⚠️ Winetricks no está instalado o no se encuentra en el PATH.\nPor favor, instala 'winetricks' en tu sistema para gestionar las dependencias."
                color = "#f87171"
            else:
                msg = f"No active Winetricks packages found in '{self.active_dep_category}'"
                color = "#71717a"

            lbl_empty = QLabel(msg)
            lbl_empty.setStyleSheet(
                f"color: {color}; font-size: 13px; font-weight: 500; padding: 24px; line-height: 1.4;"
            )
            lbl_empty.setAlignment(Qt.AlignCenter)
            lbl_empty.setWordWrap(True)
            self.dep_layout.addWidget(lbl_empty)
        else:
            for dep in filtered:
                row = QFrame()
                row.setStyleSheet(
                    "background-color: #121214; border: 1px solid #2d2d34; border-radius: 8px; padding: 12px;"
                )
                row_layout = QVBoxLayout(row)
                row_layout.setSpacing(6)

                top_layout = QHBoxLayout()

                left_layout = QHBoxLayout()
                left_layout.setSpacing(8)

                lbl_name = QLabel(dep["name"])
                lbl_name.setStyleSheet(
                    "color: #ffffff; font-weight: bold; font-size: 13px;"
                )
                lbl_name.setWordWrap(True)
                left_layout.addWidget(lbl_name)

                lbl_tag = QLabel(dep["type"])
                lbl_tag.setObjectName("AppTag")
                lbl_tag.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                left_layout.addWidget(lbl_tag)

                top_layout.addLayout(left_layout, stretch=1)

                verb = dep["verb"]
                is_installed = verb in self.installed_verbs

                if is_installed:
                    lbl_status = QLabel("✓ Installed")
                    lbl_status.setObjectName("BadgeReady")
                    top_layout.addWidget(lbl_status)

                    btn_action = QPushButton("Remove")
                    btn_action.setObjectName("RedBtnText")
                    btn_action.setCursor(Qt.PointingHandCursor)
                    btn_action.setStyleSheet(
                        "min-height: 22px; max-height: 22px; padding: 0px 12px; font-size: 11px; font-weight: bold; background-color: transparent;"
                    )
                    btn_action.clicked.connect(
                        lambda checked=False, v=verb: (
                            self.remove_dependency_requested.emit(self.prefix_name, v)
                        )
                    )
                    top_layout.addWidget(btn_action)
                else:
                    btn_action = QPushButton("Install")
                    btn_action.setObjectName("BlueBtn")
                    btn_action.setCursor(Qt.PointingHandCursor)
                    btn_action.setStyleSheet(
                        "min-height: 22px; max-height: 22px; padding: 0px 12px; font-size: 11px; font-weight: bold;"
                    )
                    btn_action.clicked.connect(
                        lambda checked=False, v=verb: (
                            self.install_dependency_requested.emit(self.prefix_name, v)
                        )
                    )
                    top_layout.addWidget(btn_action)

                row_layout.addLayout(top_layout)

                lbl_desc = QLabel(dep["desc"])
                lbl_desc.setStyleSheet("color: #71717a; font-size: 11px;")
                lbl_desc.setWordWrap(True)
                row_layout.addWidget(lbl_desc)

                self.dep_layout.addWidget(row)

        # Add a stretch at bottom
        self.dep_layout.addStretch(1)

    @Slot()
    def _on_run_installer_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Windows Installer (.exe)", "", "Executables (*.exe)"
        )
        if path:
            self.run_installer_requested.emit(self.prefix_name, path)

    @Slot()
    def _on_perf_settings_changed(self) -> None:
        self.perf_settings_changed.emit(
            self.prefix_name,
            self.chk_esync.isChecked(),
            self.chk_fsync.isChecked(),
            self.chk_sandbox.isChecked(),
        )

    @Slot()
    def _on_virtual_desktop_toggled(self) -> None:
        """Enables/disables resolution selector and emits change signal."""
        enabled = self.chk_virtual_desktop.isChecked()
        self.combo_vd_resolution.setEnabled(enabled)
        self.lbl_vd_res.setEnabled(enabled)
        resolution = self.combo_vd_resolution.currentText()
        self.virtual_desktop_changed.emit(self.prefix_name, enabled, resolution)

    @Slot(int)
    def _on_dpi_scale_changed(self, index: int) -> None:
        """Maps combo index to real DPI value and emits the change signal."""
        dpi_values = [96, 120, 144, 192]
        dpi = dpi_values[index] if 0 <= index < len(dpi_values) else 96
        self.dpi_scale_changed.emit(self.prefix_name, dpi)

    @Slot(str)
    def _on_runner_changed(self, runner_name: str) -> None:
        """Triggered when runner combo changes."""
        self.runner_changed.emit(self.prefix_name, runner_name)

    @Slot(int)
    def _on_monitor_changed(self, index: int) -> None:
        """Triggered when launch monitor changes."""
        if index < 0:
            return
        monitor_val = self.combo_monitor.itemData(index) or "default"
        self.monitor_changed.emit(self.prefix_name, monitor_val)

    def update_drives_list(self) -> None:
        """Reads symlinks under prefixes/<name>/dosdevices/ and populates virtual drives list dynamically."""
        # Clear existing layout items
        while self.drives_layout.count():
            item = self.drives_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self.prefix_name:
            return

        prefix_path = self.prefixes_dir / self.prefix_name
        dosdevices_path = prefix_path / "dosdevices"

        if not dosdevices_path.exists():
            lbl_no_devices = QLabel(
                "No se detectó el directorio de dispositivos de Wine."
            )
            lbl_no_devices.setStyleSheet(
                "color: #71717a; font-style: italic; font-size: 12px;"
            )
            self.drives_layout.addWidget(lbl_no_devices)
            return

        drives = []
        try:
            for item in dosdevices_path.iterdir():
                if item.name.endswith(":"):
                    letter = item.name[:-1].upper()
                    target = "Desconocido"
                    try:
                        if item.is_symlink():
                            target = str(item.readlink())
                        else:
                            target = str(item.resolve())
                    except Exception:
                        pass
                    drives.append((letter, target))
        except Exception as e:
            print(f"Error reading drives: {e}")

        # Sort alphabetically
        drives.sort(key=lambda x: x[0])

        for letter, target in drives:
            row = QFrame()
            row.setStyleSheet(
                "QFrame { background-color: #1c1c1e; border: 1px solid #2c2c2e; border-radius: 6px; padding: 6px 12px; }"
                "QFrame:hover { background-color: #242426; border: 1px solid #3a3a3c; }"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 4, 8, 4)
            row_layout.setSpacing(12)

            # Icon + Letter
            icon = "💽" if letter == "C" else "📁"
            lbl_letter = QLabel(f"{icon}  <b>Unidad {letter}:</b>")
            lbl_letter.setStyleSheet(
                "color: #ffffff; font-size: 13px; font-weight: bold; background: transparent; border: none;"
            )
            row_layout.addWidget(lbl_letter)

            # Arrow
            lbl_arrow = QLabel("→")
            lbl_arrow.setStyleSheet(
                "color: #8e8e93; font-size: 12px; background: transparent; border: none;"
            )
            row_layout.addWidget(lbl_arrow)

            # Target path
            lbl_target = QLabel(target)
            lbl_target.setStyleSheet(
                "color: #60a5fa; font-size: 12px; font-family: monospace; background: transparent; border: none;"
            )
            lbl_target.setWordWrap(True)
            row_layout.addWidget(lbl_target, stretch=1)

            # Action button
            if letter != "C":
                btn_del = QPushButton("Desmontar")
                btn_del.setCursor(Qt.PointingHandCursor)
                btn_del.setStyleSheet(
                    "background-color: transparent; border: 1px solid #ff453a; border-radius: 4px; "
                    "color: #ff453a; font-size: 11px; font-weight: bold; padding: 4px 10px;"
                )
                btn_del.clicked.connect(
                    lambda checked=False, ltr=letter: self._on_delete_drive_clicked(ltr)
                )
                row_layout.addWidget(btn_del)
            else:
                lbl_system = QLabel("Sistema")
                lbl_system.setStyleSheet(
                    "color: #30d158; font-size: 11px; font-weight: bold; background: transparent; border: none; padding-right: 8px;"
                )
                row_layout.addWidget(lbl_system)

            self.drives_layout.addWidget(row)

    def _on_add_drive_clicked(self) -> None:
        """Prompts user to select drive letter and directory, creating the symlink in WINEPREFIX."""
        letter, ok = QInputDialog.getText(
            self,
            "Agregar Unidad Virtual",
            "Especifica la letra para la unidad (ej: D, E, Y):",
        )
        if not (ok and letter.strip()):
            return

        letter = letter.strip().lower()
        if len(letter) != 1 or not letter.isalpha():
            QMessageBox.warning(
                self,
                "Letra Inválida",
                "Por favor ingresa una sola letra del alfabeto (A-Z).",
            )
            return

        if letter == "c":
            QMessageBox.warning(
                self,
                "Acceso Denegado",
                "La unidad C ya está reservada para el sistema estándar de Wine.",
            )
            return

        target_dir = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta para montar como unidad"
        )
        if not target_dir:
            return

        prefix_path = self.prefixes_dir / self.prefix_name
        symlink_path = prefix_path / "dosdevices" / f"{letter}:"

        # Unlink any existing first
        if symlink_path.is_symlink() or symlink_path.exists():
            try:
                symlink_path.unlink()
            except Exception:
                pass

        try:
            symlink_path.symlink_to(target_dir)
            self.update_drives_list()
            QMessageBox.information(
                self,
                "Éxito",
                f"¡Unidad {letter.upper()}: enlazada con éxito a {target_dir}!",
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"No se pudo crear la unidad virtual: {e}"
            )

    def _on_delete_drive_clicked(self, letter: str) -> None:
        """Removes a virtual drive mapping symlink."""
        res = QMessageBox.question(
            self,
            "Desmontar Unidad",
            f"¿Seguro que deseas desmontar la Unidad {letter}:?\nWine ya no podrá acceder a esta carpeta.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            prefix_path = self.prefixes_dir / self.prefix_name
            symlink_path = prefix_path / "dosdevices" / f"{letter.lower()}:"
            if symlink_path.is_symlink() or symlink_path.exists():
                try:
                    symlink_path.unlink()
                except Exception:
                    pass
            self.update_drives_list()
