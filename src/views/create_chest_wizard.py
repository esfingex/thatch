import json
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QFrame,
    QComboBox,
    QWidget,
    QSizePolicy,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
)
from PySide6.QtCore import Signal, Qt, Slot

from i18n import _


class CreateChestWizard(QDialog):
    """
    Sleek, modern 4-step wizard dialog to create a new Treasure Chest.
    Features Figma style stepper header, visual stepper, and dual pathways
    (Preset vs. Manual Custom Recipe creator).
    """

    created = Signal(str, str, str, bool)  # name, recipe_id, runner, sandbox

    def __init__(self, recipes: dict, runners: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.recipes = recipes
        self.runners = runners

        self.setWindowTitle(_("wizard_window_title"))
        self.resize(640, 520)
        self.setObjectName("WizardDialog")

        # Resolve dynamic recipes path
        # Thatch launcher base dir is src/.., config/recipes is at base_dir/config/recipes
        self.recipes_dir = Path(__file__).parent.parent.parent.resolve() / "config" / "recipes"

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # 1. Back button & Title Header
        header_layout = QHBoxLayout()
        self.btn_back_header = QPushButton(_("cdetails_btn_back"))
        self.btn_back_header.setStyleSheet(
            "background-color: transparent; border: none; color: #a1a1aa; font-weight: bold;"
        )
        self.btn_back_header.setCursor(Qt.PointingHandCursor)
        self.btn_back_header.clicked.connect(self.reject)

        header_title_layout = QVBoxLayout()
        self.lbl_wizard_title = QLabel(_("wizard_title"))
        self.lbl_wizard_title.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")
        self.lbl_wizard_subtitle = QLabel(_("wizard_subtitle"))
        self.lbl_wizard_subtitle.setStyleSheet("color: #71717a; font-size: 12px;")
        header_title_layout.addWidget(self.lbl_wizard_title)
        header_title_layout.addWidget(self.lbl_wizard_subtitle)

        header_layout.addWidget(self.btn_back_header)
        header_layout.addSpacing(10)
        header_layout.addLayout(header_title_layout)
        header_layout.addStretch(1)
        main_layout.addLayout(header_layout)

        # 2. Figma Style Stepper Header
        stepper_layout = QHBoxLayout()
        stepper_layout.setContentsMargins(40, 0, 40, 0)
        stepper_layout.setSpacing(0)

        self.step_circles = []
        self.step_lines = []

        for i in range(1, 5):
            circle = QLabel(str(i))
            circle.setObjectName("StepCircleInactive")
            circle.setAlignment(Qt.AlignCenter)
            self.step_circles.append(circle)
            stepper_layout.addWidget(circle)

            if i < 4:
                line = QFrame()
                line.setObjectName("StepLine")
                line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                self.step_lines.append(line)
                stepper_layout.addWidget(line)

        main_layout.addLayout(stepper_layout)

        # 3. Stacked widget for the steps
        self.step_stack = QStackedWidget()
        main_layout.addWidget(self.step_stack, stretch=1)

        # Step 1 Widget: Name Chest
        self.step1_widget = self._create_step1()
        self.step_stack.addWidget(self.step1_widget)

        # Step 2 Widget: Choose Configuration Mode (Preset vs Manual)
        self.step2_widget = self._create_step2()
        self.step_stack.addWidget(self.step2_widget)

        # Step 3 Widget: Select Runner
        self.step3_widget = self._create_step3()
        self.step_stack.addWidget(self.step3_widget)

        # Step 4 Widget: Review & Confirm
        self.step4_widget = self._create_step4()
        self.step_stack.addWidget(self.step4_widget)

        # 4. Navigation Buttons (Bottom)
        bottom_layout = QHBoxLayout()

        self.btn_prev = QPushButton(_("wizard_btn_prev"))
        self.btn_prev.setCursor(Qt.PointingHandCursor)
        self.btn_prev.clicked.connect(self._on_prev)

        self.btn_next = QPushButton(_("wizard_btn_next"))
        self.btn_next.setObjectName("BlueBtn")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.clicked.connect(self._on_next)

        bottom_layout.addWidget(self.btn_prev)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.btn_next)
        main_layout.addLayout(bottom_layout)

        self.current_step = 0
        self._update_stepper()

    def _create_step1(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("DetailCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(_("wizard_step1_title"))
        title.setObjectName("CardTitle")
        title.setStyleSheet("font-size: 18px;")

        subtitle = QLabel(_("wizard_step1_subtitle"))
        subtitle.setStyleSheet("color: #71717a; font-size: 13px;")

        self.txt_chest_name = QLineEdit()
        self.txt_chest_name.setPlaceholderText(_("wizard_step1_placeholder"))
        self.txt_chest_name.textChanged.connect(self._validate_step1)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.txt_chest_name)
        layout.addStretch(1)
        return widget

    def _create_step2(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("DetailCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel(_("wizard_step2_title"))
        title.setObjectName("CardTitle")
        title.setStyleSheet("font-size: 18px;")
        layout.addWidget(title)

        subtitle = QLabel(_("wizard_step2_subtitle"))
        subtitle.setStyleSheet("color: #71717a; font-size: 13px; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # Dual choice radio buttons
        self.mode_group = QButtonGroup(self)

        self.radio_preset = QRadioButton(_("wizard_radio_preset"))
        self.radio_preset.setChecked(True)
        self.radio_preset.setStyleSheet("font-weight: bold; color: #ffffff;")
        self.radio_preset.setCursor(Qt.PointingHandCursor)
        self.mode_group.addButton(self.radio_preset)
        layout.addWidget(self.radio_preset)

        self.radio_manual = QRadioButton(_("wizard_radio_manual"))
        self.radio_manual.setStyleSheet("font-weight: bold; color: #ffffff;")
        self.radio_manual.setCursor(Qt.PointingHandCursor)
        self.mode_group.addButton(self.radio_manual)
        layout.addWidget(self.radio_manual)

        # Connect stack switcher
        self.radio_preset.toggled.connect(self._on_mode_toggled)
        self.radio_manual.toggled.connect(self._on_mode_toggled)

        # Stacked area for selections
        self.mode_stack = QStackedWidget()
        self.mode_stack.setStyleSheet("background-color: transparent; border: none;")
        layout.addWidget(self.mode_stack, stretch=1)

        # Page 0: Preset mode view
        preset_page = QWidget()
        pres_layout = QVBoxLayout(preset_page)
        pres_layout.setContentsMargins(0, 8, 0, 0)
        pres_layout.setSpacing(8)

        lbl_pres_desc = QLabel(_("wizard_lbl_preset_desc"))
        lbl_pres_desc.setObjectName("CardLabel")
        self.combo_env = QComboBox()
        for rid, rdata in self.recipes.items():
            self.combo_env.addItem(rdata.get("display_name", rid), rid)

        # Sandbox for Presets pathway too
        self.chk_sandbox_preset = QCheckBox(_("wizard_chk_sandbox"))
        self.chk_sandbox_preset.setChecked(False)
        self.chk_sandbox_preset.setStyleSheet("color: #60a5fa; font-weight: bold; margin-top: 8px;")
        self.chk_sandbox_preset.setToolTip(_("wizard_tooltip_sandbox"))

        pres_layout.addWidget(lbl_pres_desc)
        pres_layout.addWidget(self.combo_env)
        pres_layout.addWidget(self.chk_sandbox_preset)
        pres_layout.addStretch(1)
        self.mode_stack.addWidget(preset_page)

        # Page 1: Manual configuration view
        manual_page = QWidget()
        man_layout = QVBoxLayout(manual_page)
        man_layout.setContentsMargins(0, 8, 0, 0)
        man_layout.setSpacing(10)

        lbl_man_title = QLabel(_("wizard_lbl_manual_title"))
        lbl_man_title.setObjectName("CardLabel")
        lbl_man_title.setStyleSheet("font-weight: bold;")
        man_layout.addWidget(lbl_man_title)

        # Name of manual recipe
        self.txt_manual_display_name = QLineEdit()
        self.txt_manual_display_name.setPlaceholderText(_("wizard_manual_name_placeholder"))
        man_layout.addWidget(self.txt_manual_display_name)

        # Performance variables checkboxes
        lbl_perf = QLabel(_("wizard_lbl_perf"))
        lbl_perf.setObjectName("CardLabel")
        man_layout.addWidget(lbl_perf)

        self.chk_esync = QCheckBox("WINEESYNC = 1")
        self.chk_esync.setChecked(True)
        self.chk_esync.setToolTip(_("wizard_tooltip_esync"))

        self.chk_fsync = QCheckBox("WINEFSYNC = 1")
        self.chk_fsync.setChecked(True)
        self.chk_fsync.setToolTip(_("wizard_tooltip_fsync"))

        self.chk_laa = QCheckBox("PROTON_FORCE_LARGE_ADDRESS_AWARE = 1")
        self.chk_laa.setChecked(True)
        self.chk_laa.setToolTip(_("wizard_tooltip_laa"))

        self.chk_sandbox = QCheckBox(_("wizard_chk_sandbox"))
        self.chk_sandbox.setChecked(False)
        self.chk_sandbox.setStyleSheet("color: #60a5fa; font-weight: bold;")
        self.chk_sandbox.setToolTip(_("wizard_tooltip_sandbox"))

        man_layout.addWidget(self.chk_esync)
        man_layout.addWidget(self.chk_fsync)
        man_layout.addWidget(self.chk_laa)
        man_layout.addWidget(self.chk_sandbox)

        # Custom winetricks verbs input
        lbl_verbs = QLabel(_("wizard_lbl_verbs"))
        lbl_verbs.setObjectName("CardLabel")
        self.txt_manual_verbs = QLineEdit()
        self.txt_manual_verbs.setPlaceholderText(_("wizard_verbs_placeholder"))
        man_layout.addWidget(lbl_verbs)
        man_layout.addWidget(self.txt_manual_verbs)

        man_layout.addStretch(1)
        self.mode_stack.addWidget(manual_page)

        return widget

    @Slot()
    def _on_mode_toggled(self) -> None:
        if self.radio_preset.isChecked():
            self.mode_stack.setCurrentIndex(0)
        else:
            self.mode_stack.setCurrentIndex(1)

    def _create_step3(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("DetailCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(_("wizard_step3_title"))
        title.setObjectName("CardTitle")
        title.setStyleSheet("font-size: 18px;")

        subtitle = QLabel(_("wizard_step3_subtitle"))
        subtitle.setStyleSheet("color: #71717a; font-size: 13px;")

        self.combo_runner = QComboBox()

        # Always add the System Wine option as a primary baseline
        self.combo_runner.addItem("Wine del Sistema (/usr/bin/wine)", "system_wine")

        # Add custom downloaded/community runners if available
        if self.runners:
            for runner in self.runners:
                self.combo_runner.addItem(_("wizard_runner_community", runner=runner), runner)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.combo_runner)
        layout.addStretch(1)
        return widget

    def _create_step4(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("DetailCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel(_("wizard_step4_title"))
        title.setObjectName("CardTitle")
        title.setStyleSheet("font-size: 18px;")

        subtitle = QLabel(_("wizard_step4_subtitle"))
        subtitle.setStyleSheet("color: #71717a; font-size: 13px;")

        grid_frame = QFrame()
        grid_frame.setStyleSheet(
            "background-color: #121214; border: 1px solid #2d2d34; border-radius: 8px; padding: 12px;"
        )
        grid_layout = QVBoxLayout(grid_frame)
        grid_layout.setSpacing(10)

        self.lbl_review_name = QLabel(_("wizard_review_name"))
        self.lbl_review_name.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        self.lbl_review_mode = QLabel(_("wizard_review_mode"))
        self.lbl_review_mode.setStyleSheet("color: #e4e4e7; font-size: 13px;")
        self.lbl_review_env = QLabel(_("wizard_review_env"))
        self.lbl_review_env.setStyleSheet("color: #e4e4e7; font-size: 13px;")
        self.lbl_review_runner = QLabel(_("wizard_review_runner"))
        self.lbl_review_runner.setStyleSheet("color: #e4e4e7; font-size: 13px;")

        grid_layout.addWidget(self.lbl_review_name)
        grid_layout.addWidget(self.lbl_review_mode)
        grid_layout.addWidget(self.lbl_review_env)
        grid_layout.addWidget(self.lbl_review_runner)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(grid_frame)
        layout.addStretch(1)
        return widget

    def _validate_step1(self) -> None:
        """Validates chest name is not empty."""
        name = self.txt_chest_name.text().strip()
        self.btn_next.setEnabled(len(name) > 0)

    def _update_stepper(self) -> None:
        """Updates numeric active stepper UI."""
        # Enable/Disable previous button
        self.btn_prev.setEnabled(self.current_step > 0)

        # Set next button text
        if self.current_step == 3:
            self.btn_next.setText(_("wizard_btn_create"))
        else:
            self.btn_next.setText(_("wizard_btn_next"))

        # Stepper active items
        for idx, circle in enumerate(self.step_circles):
            if idx == self.current_step:
                circle.setObjectName("StepCircleActive")
            else:
                circle.setObjectName("StepCircleInactive")

            # Apply styling changes
            circle.style().unpolish(circle)
            circle.style().polish(circle)

        # Lines style highlighting
        for idx, line in enumerate(self.step_lines):
            if idx < self.current_step:
                line.setStyleSheet("background-color: #2563eb;")
            else:
                line.setStyleSheet("background-color: #27272a;")

        # Validate button
        if self.current_step == 0:
            self._validate_step1()
        else:
            self.btn_next.setEnabled(True)

    @Slot()
    def _on_next(self) -> None:
        if self.current_step < 3:
            self.current_step += 1
            self.step_stack.setCurrentIndex(self.current_step)

            # Prefill step 4 data
            if self.current_step == 3:
                name = self.txt_chest_name.text().strip()
                is_preset = self.radio_preset.isChecked()
                mode_str = _("wizard_mode_preset") if is_preset else _("wizard_mode_manual")

                if is_preset:
                    env = self.combo_env.currentText()
                else:
                    manual_display = self.txt_manual_display_name.text().strip() or _(
                        "wizard_manual_fallback", name=name
                    )
                    env = manual_display

                runner = self.combo_runner.currentText()
                self.lbl_review_name.setText(_("wizard_review_name_value", name=name))
                self.lbl_review_mode.setText(_("wizard_review_mode_value", mode=mode_str))
                self.lbl_review_env.setText(_("wizard_review_env_value", env=env))
                self.lbl_review_runner.setText(_("wizard_review_runner_value", runner=runner))

            self._update_stepper()
        else:
            # Emit create and close
            name = self.txt_chest_name.text().strip().replace(" ", "_").lower()
            runner = self.combo_runner.currentData() or "Wine del Sistema (/usr/bin/wine)"
            if runner == "system_wine":
                runner = "Wine del Sistema (/usr/bin/wine)"

            sandbox_enabled = False
            recipe_id = ""
            if self.radio_preset.isChecked():
                recipe_id = self.combo_env.currentData()
                sandbox_enabled = self.chk_sandbox_preset.isChecked()
            else:
                # Custom Manual pathway
                # Build custom JSON dynamically to make it distributable!
                recipe_id = f"recipe_{name}"
                display_name = (
                    self.txt_manual_display_name.text().strip()
                    or f"Custom {name.replace('_', ' ').title()}"
                )
                sandbox_enabled = self.chk_sandbox.isChecked()

                # Performance variables
                perf_env = {}
                if self.chk_esync.isChecked():
                    perf_env["WINEESYNC"] = "1"
                if self.chk_fsync.isChecked():
                    perf_env["WINEFSYNC"] = "1"
                if self.chk_laa.isChecked():
                    perf_env["PROTON_FORCE_LARGE_ADDRESS_AWARE"] = "1"

                # Required winetricks verbs
                verbs_raw = self.txt_manual_verbs.text().strip()
                required_verbs = []
                if verbs_raw:
                    required_verbs = [v.strip() for v in verbs_raw.split(",") if v.strip()]

                # Assembly recipe dict
                new_recipe = {
                    "recipe_id": recipe_id,
                    "display_name": display_name,
                    "description": "Receta personalizada autogenerada desde Thatch UI.",
                    "recommended_runner": runner,
                    "performance_env": perf_env,
                    "required_verbs": required_verbs,
                }

                # Save as standalone .json in config/recipes/
                try:
                    self.recipes_dir.mkdir(parents=True, exist_ok=True)
                    json_path = self.recipes_dir / f"{recipe_id}.json"
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(new_recipe, f, indent=4, ensure_ascii=False)

                    # Also append in-memory recipes dictionary so it is immediately registered
                    self.recipes[recipe_id] = new_recipe
                except Exception as e:
                    print(f"[WIZARD] Error saving custom dynamic recipe JSON: {e}")

            self.created.emit(name, recipe_id, runner, sandbox_enabled)
            self.accept()

    @Slot()
    def _on_prev(self) -> None:
        if self.current_step > 0:
            self.current_step -= 1
            self.step_stack.setCurrentIndex(self.current_step)
            self._update_stepper()
