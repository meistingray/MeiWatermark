from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent, QIcon, QImage, QIntValidator, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .export import ExportWorker
from .i18n import translate
from .model import Anchor, ExportSettings, LayerKind, ResizeMode, Unit, WatermarkLayer
from .presets import (
    load_export_presets,
    load_watermark_presets,
    save_export_preset,
    save_watermark_preset,
)
from .render import estimate_size, export_size, load_image, load_preview, render, system_fonts


ACCENT = "#A40B5E"
IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp)"


def display_image_name(path: Path) -> str:
    return path.name[:11] + "…" if len(path.name) > 12 else path.name


def pen_icon() -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(ACCENT), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(7, 14, 17, 4)
    painter.setPen(QPen(QColor("#5b0635"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(5, 16, 8, 13)
    painter.end()
    return QIcon(pixmap)


class LayerRow(QWidget):
    def __init__(self, owner: QListWidget, item: QListWidgetItem, layer: WatermarkLayer, edit, name_text: str, edit_tooltip: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.owner, self.item, self.drag_start = owner, item, None
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 0, 4, 0)
        name = QLabel(name_text)
        self.name_label = name
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(name)
        layout.addStretch()
        if layer.kind is LayerKind.TEXT:
            button = QToolButton()
            button.setObjectName("editLayer")
            button.setIcon(pen_icon())
            button.setIconSize(QSize(20, 20))
            button.setFixedSize(28, 28)
            button.setAutoRaise(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setToolTip(edit_tooltip)
            button.setStyleSheet("padding: 0 0 4px 0;")
            button.clicked.connect(edit)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        drag = QLabel("⠿")
        drag.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(drag, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.owner.setCurrentItem(self.item)
        self.drag_start = event.position()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.drag_start and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position() - self.drag_start).manhattanLength() >= 4:
                self.owner.startDrag(Qt.DropAction.MoveAction)
        event.accept()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MeiWatermark")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "logo.png")))
        self.resize(1280, 800)
        self.setMinimumSize(960, 620)
        self.setAcceptDrops(True)
        self.language = "zh"
        self.paths: list[Path] = []
        self.layers: list[WatermarkLayer] = []
        self.source = None
        self.settings = ExportSettings()
        self.worker: ExportWorker | None = None
        self._loading_controls = False
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.estimate_timer = QTimer(self)
        self.estimate_timer.setSingleShot(True)
        self.estimate_timer.timeout.connect(self.update_estimate)
        self._build_ui()
        self._apply_style()
        self.refresh_presets()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        layout.addLayout(self._action_row())
        layout.addWidget(self._body(), 1)
        self.setCentralWidget(root)
        self.status = self.statusBar()
        self.status.showMessage(self.t("拖拽图片到窗口任意位置即可导入"))

    def t(self, text: str) -> str:
        return translate(text, self.language)

    def set_language(self, language: str) -> None:
        if language == self.language:
            return
        selected_path = self.thumbnails.currentItem().data(Qt.ItemDataRole.UserRole) if self.thumbnails.currentItem() else None
        selected_layer = self.layer_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.layer_list.currentItem() else None
        self.language = language
        old = self.takeCentralWidget()
        self.menuBar().clear()
        self._build_ui()
        self._apply_style()
        self.refresh_presets()
        paths, self.paths = self.paths, []
        self.add_paths(paths)
        layers, self.layers = self.layers, []
        for layer in layers:
            self.add_layer(layer)
        self.format.setCurrentText(self.settings.format)
        self.quality.setValue(self.settings.quality)
        self.resize_mode.setCurrentIndex(list(ResizeMode).index(self.settings.resize_mode))
        self.resize_value.setText(str(round(self.settings.resize_value)) if self.settings.resize_value else "")
        self.allow_upscale.setChecked(self.settings.allow_upscale)
        self.keep_exif.setChecked(self.settings.keep_exif)
        self.keep_icc.setChecked(self.settings.keep_icc)
        self.output_path.setText(self.settings.output_path)
        for row in range(self.thumbnails.count()):
            if self.thumbnails.item(row).data(Qt.ItemDataRole.UserRole) == selected_path:
                self.thumbnails.setCurrentRow(row)
        for row in range(self.layer_list.count()):
            if self.layer_list.item(row).data(Qt.ItemDataRole.UserRole) == selected_layer:
                self.layer_list.setCurrentRow(row)
        if old is not None:
            old.deleteLater()

    def _build_menu(self) -> None:
        language = self.menuBar().addMenu("Language")
        for code, label in (("zh", "中文"), ("en", "English"), ("es", "Español"), ("ja", "日本語")):
            action = language.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == self.language)
            action.triggered.connect(lambda _, value=code: self.set_language(value))
        about = QAction("About", self)
        about.triggered.connect(self.show_about)
        self.menuBar().addAction(about)

    def _action_row(self) -> QHBoxLayout:
        self._build_menu()
        row = QHBoxLayout()
        row.setSpacing(5)
        open_button = QPushButton(self.t("打开图片"))
        open_button.setObjectName("primary")
        open_button.clicked.connect(self.open_images)
        row.addWidget(open_button)
        image_button = QPushButton(self.t("添加图片水印"))
        image_button.clicked.connect(self.add_image_layer)
        row.addWidget(image_button)
        text_button = QPushButton(self.t("添加文字水印"))
        text_button.clicked.connect(self.add_text_layer)
        row.addWidget(text_button)
        row.addStretch()
        self.watermark_preset = QComboBox()
        self.watermark_preset.addItem(self.t("水印预设"))
        self.watermark_preset.currentTextChanged.connect(self.apply_watermark_preset)
        row.addWidget(self.watermark_preset)
        save = QPushButton(self.t("保存"))
        save.setObjectName("presetSave")
        save.clicked.connect(self.save_watermark_preset)
        row.addWidget(save)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFixedHeight(24)
        row.addWidget(separator)
        self.export_preset = QComboBox()
        self.export_preset.addItem(self.t("导出预设"))
        self.export_preset.currentTextChanged.connect(self.apply_export_preset)
        row.addWidget(self.export_preset)
        save = QPushButton(self.t("保存"))
        save.setObjectName("presetSave")
        save.clicked.connect(self.save_export_preset)
        row.addWidget(save)
        return row

    def _body(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._layers_panel())
        splitter.addWidget(self._preview_panel())
        splitter.addWidget(self._export_panel())
        splitter.setSizes([245, 720, 285])
        return splitter

    def _layers_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidePanel")
        panel.setMaximumWidth(270)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self._heading(self.t("水印图层")))
        self.layer_list = QListWidget()
        self.layer_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.layer_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.layer_list.currentItemChanged.connect(lambda *_: self.load_layer_controls())
        self.layer_list.itemDoubleClicked.connect(self.edit_text_layer)
        self.layer_list.itemChanged.connect(self.update_layer_visibility)
        self.layer_list.model().rowsMoved.connect(lambda *_: self.sync_layer_order())
        layout.addWidget(self.layer_list, 1)
        layout.addWidget(self._line())
        layout.addWidget(self._heading(self.t("选中图层属性")))
        controls = QFrame()
        controls.setObjectName("propertyPanel")
        properties = QVBoxLayout(controls)
        properties.setContentsMargins(7, 7, 7, 7)
        properties.setSpacing(5)
        self.size_value, self.size_unit = self._number_unit(24, [self.t("百分比"), "px"])
        properties.addWidget(self._property_row(self.t("大小"), self._stepper(self.size_value, 0, 100000), self.size_unit))
        self.opacity = QLineEdit("80")
        self.opacity.setValidator(QIntValidator(0, 100, self))
        properties.addWidget(self._property_row(self.t("透明度"), self._stepper(self.opacity, 0, 100)))
        self.horizontal_value, self.horizontal_unit = self._number_unit(2, [self.t("视觉比例"), self.t("百分比"), "px"], -100000)
        properties.addWidget(self._property_row(self.t("水平内嵌"), self._stepper(self.horizontal_value, -100000, 100000), self.horizontal_unit))
        self.vertical_value, self.vertical_unit = self._number_unit(2, [self.t("视觉比例"), self.t("百分比"), "px"], -100000)
        properties.addWidget(self._property_row(self.t("垂直内嵌"), self._stepper(self.vertical_value, -100000, 100000), self.vertical_unit))
        self.rotation = QLineEdit("0")
        self.rotation.setValidator(QIntValidator(-180, 180, self))
        properties.addWidget(self._property_row(self.t("旋转"), self._stepper(self.rotation, -180, 180)))
        layout.addWidget(controls)
        layout.addWidget(self._heading(self.t("九宫格定位")))
        grid_widget = QWidget()
        grid_widget.setObjectName("anchorGrid")
        self.anchor_buttons = []
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(4)
        for index, anchor in enumerate(Anchor):
            button = QToolButton()
            button.setObjectName("anchor")
            button.setText("○")
            button.setCheckable(True)
            button.setFixedSize(34, 34)
            button.setProperty("anchor", anchor)
            button.clicked.connect(lambda checked, value=anchor: self.set_anchor(value))
            self.anchor_buttons.append(button)
            grid.addWidget(button, index // 3, index % 3)
        layout.addWidget(grid_widget)
        for widget in (self.size_value, self.size_unit, self.opacity, self.horizontal_value, self.horizontal_unit, self.vertical_value, self.vertical_unit, self.rotation):
            if isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(lambda *_: self.store_layer_controls())
            else:
                widget.textChanged.connect(lambda *_: self.store_layer_controls())
        return panel

    def _preview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        heading = QHBoxLayout()
        heading.addWidget(self._heading(self.t("实时预览")))
        heading.addStretch()
        remove = QPushButton(self.t("移除照片"))
        remove.clicked.connect(self.remove_selected_photo)
        heading.addWidget(remove)
        layout.addLayout(heading)
        self.preview = QLabel(self.t("拖拽图片到窗口任意位置即可导入"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("preview")
        self.preview.setMinimumSize(420, 360)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self._line())
        self.thumbnails = QListWidget()
        self.thumbnails.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbnails.setFlow(QListWidget.Flow.LeftToRight)
        self.thumbnails.setWrapping(False)
        self.thumbnails.setIconSize(QSize(94, 70))
        self.thumbnails.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbnails.setFixedHeight(108)
        self.thumbnails.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumbnails.customContextMenuRequested.connect(self.show_thumbnail_menu)
        self.thumbnails.currentRowChanged.connect(self.select_photo)
        remove_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.thumbnails)
        remove_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        remove_shortcut.activated.connect(self.remove_selected_photo)
        layout.addWidget(self.thumbnails)
        return panel

    def _export_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidePanel")
        panel.setMaximumWidth(290)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 5, 5, 5)
        layout.addWidget(self._heading(self.t("导出设置")))
        form = QFormLayout()
        self.format = QComboBox()
        self.format.addItems(["JPEG", "PNG", "WEBP"])
        form.addRow(self.t("格式"), self.format)
        self.quality = QSlider(Qt.Orientation.Horizontal)
        self.quality.setRange(1, 100)
        self.quality.setValue(100)
        self.quality_number = QLabel("100")
        quality_row = QHBoxLayout()
        quality_row.addWidget(self.quality)
        quality_row.addWidget(self.quality_number)
        form.addRow(self.t("质量"), quality_row)
        self.resize_mode = QComboBox()
        self.resize_mode.addItems([self.t(value) for value in ("不约束", "最长边", "最短边", "比例")])
        form.addRow(self.t("尺寸约束"), self.resize_mode)
        self.resize_value = QLineEdit()
        self.resize_value.setValidator(QIntValidator(1, 100000, self))
        self.resize_value.setEnabled(False)
        self.resize_value_label = QLabel(f"{self.t('约束数值')} (px)")
        form.addRow(self.resize_value_label, self.resize_value)
        self.allow_upscale = QCheckBox(self.t("不放大"))
        form.addRow(self.allow_upscale)
        self.keep_exif = QCheckBox(self.t("保留 EXIF"))
        self.keep_exif.setChecked(True)
        form.addRow(self.keep_exif)
        self.keep_icc = QCheckBox(self.t("保留 ICC"))
        self.keep_icc.setChecked(True)
        form.addRow(self.keep_icc)
        layout.addLayout(form)
        layout.addStretch()
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("支持相对路径 /Mei" if self.language == "zh" else "")
        choose_output = QPushButton(self.t("选择"))
        choose_output.clicked.connect(self.select_output_path)
        clear_output = QPushButton(self.t("清空"))
        clear_output.clicked.connect(self.output_path.clear)
        layout.addWidget(QLabel(self.t("导出路径")))
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_path, 1)
        output_row.addWidget(choose_output)
        output_row.addWidget(clear_output)
        layout.addLayout(output_row)
        layout.addWidget(self._line())
        layout.addWidget(self._heading(self.t("预计文件大小")))
        self.current_estimate = QLabel(self.t("当前照片约 —"))
        self.batch_estimate = QLabel(self.t("本批次约 —"))
        layout.addWidget(self.current_estimate)
        layout.addWidget(self.batch_estimate)
        self.export_button = QPushButton(self.t("导出"))
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self.export_batch)
        layout.addWidget(self.export_button)
        self.quality.valueChanged.connect(self.update_export_settings)
        self.format.currentTextChanged.connect(self.update_export_settings)
        self.resize_mode.currentIndexChanged.connect(lambda *_: self.resize_mode_changed())
        self.resize_value.textChanged.connect(self.update_export_settings)
        self.allow_upscale.toggled.connect(self.update_export_settings)
        self.keep_exif.toggled.connect(self.update_export_settings)
        self.keep_icc.toggled.connect(self.update_export_settings)
        self.output_path.textChanged.connect(self.update_export_settings)
        return panel

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("heading")
        return label

    @staticmethod
    def _line() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        return line

    @staticmethod
    def _number_unit(value: int, units: list[str], minimum: int = 0) -> tuple[QLineEdit, QComboBox]:
        number = QLineEdit(str(value))
        number.setValidator(QIntValidator(minimum, 100000))
        unit = QComboBox()
        unit.addItems(units)
        return number, unit

    def _stepper(self, field: QLineEdit, minimum: int, maximum: int) -> QWidget:
        field.setMaximumWidth(58)
        wrapper = QWidget()
        wrapper.setObjectName("stepper")
        wrapper.setFixedWidth(108)
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        for label, delta in (("−", -1), ("+", 1)):
            button = QToolButton()
            button.setText(label)
            button.setObjectName("step")
            button.setFixedSize(23, 26)
            button.clicked.connect(lambda _, amount=delta: field.setText(str(max(minimum, min(maximum, self._number(field) + amount)))))
            if delta < 0:
                row.addWidget(button)
            else:
                plus = button
        row.addWidget(field)
        row.addWidget(plus)
        return wrapper

    @staticmethod
    def _property_row(label: str, editor: QWidget, unit: QComboBox | None = None) -> QWidget:
        widget = QWidget()
        widget.setObjectName("propertyRow")
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        name = QLabel(label)
        name.setFixedWidth(52)
        row.addWidget(name)
        row.addWidget(editor)
        if unit is not None:
            unit.setFixedWidth(74)
            row.addWidget(unit)
        else:
            row.addStretch()
        return widget

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QWidget {{ font-size: 12px; color: #202124; }}
            QMainWindow, QWidget {{ background: #f5f6f8; }}
            QMenuBar {{ background: #ffffff; border-bottom: 1px solid #e3e5e8; padding: 1px 3px; }}
            QMenuBar::item {{ padding: 4px 8px; background: transparent; }}
            QMenuBar::item:selected {{ background: #eceef2; }}
            QPushButton, QComboBox, QLineEdit {{ min-height: 24px; border: 1px solid #d7dbe1; border-radius: 2px; padding: 1px 7px; background: #fff; }}
            QPushButton:hover, QComboBox:hover {{ border-color: {ACCENT}; }}
            QPushButton#primary {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT}; font-weight: 600; }}
            QPushButton#presetSave {{ color: {ACCENT}; border-color: {ACCENT}; font-weight: 600; }}
            QLabel#heading {{ font-size: 13px; font-weight: 600; margin: 2px 0; }}
            QLabel#preview {{ background: #262a30; border: 1px solid #363b43; color: #c8ccd2; }}
            QWidget#sidePanel {{ background: #ffffff; }}
            QWidget#sidePanel QLabel, QWidget#sidePanel QCheckBox {{ background: transparent; }}
            QListWidget {{ background: #fff; border: 1px solid #d9dde3; border-radius: 0; padding: 2px; }}
            QListWidget::item {{ padding: 5px; border-radius: 0; }}
            QListWidget::item:selected {{ background: #f5dce9; border: 1px solid {ACCENT}; }}
            QListWidget::item:focus {{ outline: none; }}
            QToolButton:checked {{ color: {ACCENT}; }}
            QToolButton#editLayer {{ border: none; background: transparent; padding: 0; }}
            QToolButton#editLayer:hover {{ background: #f5dce9; border-radius: 4px; }}
            QToolButton#step {{ min-width: 20px; border: 1px solid #d7dbe1; border-radius: 2px; background: #fff; font-weight: 600; }}
            QToolButton#step:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
            QToolButton#anchor {{ border: none; background: transparent; border-radius: 17px; font-size: 21px; color: #7b818a; }}
            QToolButton#anchor:checked {{ border: none; background: #f9e3ef; color: {ACCENT}; }}
            QFrame#propertyPanel {{ background: #ffffff; border: 1px solid #dfe2e7; border-radius: 3px; }}
            QFrame#propertyPanel QLabel, QWidget#propertyRow, QWidget#stepper, QWidget#anchorGrid {{ background: transparent; }}
            QSlider::groove:horizontal {{ height: 3px; background: #dedede; }}
            QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -5px 0; border-radius: 6px; background: {ACCENT}; }}
            QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
        """)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self.add_paths([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def open_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "打开图片", "", IMAGE_FILTER)
        self.add_paths([Path(file) for file in files])

    def add_paths(self, paths: list[Path]) -> None:
        supported = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
        added = [path for path in paths if path.is_file() and path.suffix.lower() in supported and path not in self.paths]
        if not added:
            return
        self.paths.extend(added)
        for path in added:
            item = QListWidgetItem(display_image_name(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            try:
                image = load_image(path).image
                image.thumbnail((240, 180), Image.Resampling.LANCZOS)
                item.setIcon(self._pixmap(image))
            except Exception:  # noqa: BLE001
                pass
            self.thumbnails.addItem(item)
        if self.thumbnails.currentRow() < 0:
            self.thumbnails.setCurrentRow(0)
        self.status.showMessage(f"已导入 {len(added)} 张图片", 3000)

    def select_photo(self, row: int) -> None:
        if row < 0:
            return
        path = self.thumbnails.item(row).data(Qt.ItemDataRole.UserRole)
        try:
            self.source = load_preview(path, (1200, 1200))
            self.schedule_preview()
            self.schedule_estimate()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "无法读取图片", str(exc))

    def remove_selected_photo(self) -> None:
        row = self.thumbnails.currentRow()
        if row < 0:
            return
        item = self.thumbnails.takeItem(row)
        self.paths.remove(item.data(Qt.ItemDataRole.UserRole))
        if self.thumbnails.count():
            self.thumbnails.setCurrentRow(min(row, self.thumbnails.count() - 1))
        else:
            self.source = None
            self.preview.setText("拖拽图片到窗口任意位置即可导入")
            self.preview.setPixmap(QPixmap())
            self.current_estimate.setText("当前照片约 —")
            self.batch_estimate.setText("本批次约 —")

    def show_thumbnail_menu(self, position) -> None:  # type: ignore[no-untyped-def]
        item = self.thumbnails.itemAt(position)
        if item is None:
            return
        self.thumbnails.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("从列表移除", self.remove_selected_photo)
        menu.exec(self.thumbnails.viewport().mapToGlobal(position))

    def add_image_layer(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择水印图片", "", IMAGE_FILTER)
        if path:
            self.add_layer(WatermarkLayer(LayerKind.IMAGE, "图片水印", image_path=path))

    def add_text_layer(self) -> None:
        layer = WatermarkLayer(LayerKind.TEXT, "文字水印", text="MeiStingray")
        if self.edit_text_dialog(layer):
            self.add_layer(layer)

    def add_layer(self, layer: WatermarkLayer) -> None:
        self.layers.append(layer)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, layer.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked)
        item.setSizeHint(QSize(0, 28))
        self.layer_list.addItem(item)
        layer_label = layer.text if layer.kind is LayerKind.TEXT else self.t(layer.name)
        self.layer_list.setItemWidget(item, LayerRow(self.layer_list, item, layer, lambda: self.edit_text_layer(item), layer_label, self.t("编辑文字水印")))
        self.layer_list.setCurrentItem(item)
        self.schedule_preview()
        self.schedule_estimate()

    def edit_text_layer(self, item: QListWidgetItem) -> None:
        layer_id = item.data(Qt.ItemDataRole.UserRole)
        layer = next((candidate for candidate in self.layers if candidate.id == layer_id), None)
        if layer is None or layer.kind is not LayerKind.TEXT:
            return
        if self.edit_text_dialog(layer):
            row = self.layer_list.itemWidget(item)
            if isinstance(row, LayerRow):
                row.name_label.setText(layer.text)
            self.schedule_preview()
            self.schedule_estimate()

    def edit_text_dialog(self, layer: WatermarkLayer) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("文字水印"))
        form = QFormLayout(dialog)
        text = QLineEdit(layer.text)
        form.addRow(self.t("文字"), text)
        font = QComboBox()
        font.addItem(self.t("系统默认"), "")
        for name, path in system_fonts().items():
            font.addItem(name, path)
        font.setCurrentIndex(max(0, font.findData(layer.font_path)))
        form.addRow(self.t("字体"), font)
        text_color = QPushButton()
        stroke_color = QPushButton()

        def set_color(button: QPushButton, title: str) -> None:
            color = QColorDialog.getColor(button.property("color"), dialog, title)
            if color.isValid():
                button.setProperty("color", color)
                button.setStyleSheet(f"background: {color.name()};")

        for button, color, title in ((text_color, layer.color, "文字颜色"), (stroke_color, layer.stroke_color, "边框颜色")):
            button.setProperty("color", QColor(*color))
            button.setStyleSheet(f"background: rgb({color[0]}, {color[1]}, {color[2]});")
            button.clicked.connect(lambda _, target=button, label=title: set_color(target, self.t(label)))
        form.addRow(self.t("文字颜色"), text_color)
        form.addRow(self.t("边框颜色"), stroke_color)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or not text.text().strip():
            return False
        layer.text = text.text().strip()
        layer.font_path = font.currentData() or None
        layer.color = tuple(text_color.property("color").getRgb()[:3])
        layer.stroke_color = tuple(stroke_color.property("color").getRgb()[:3])
        return True

    def current_layer(self) -> WatermarkLayer | None:
        item = self.layer_list.currentItem()
        if item is None:
            return None
        layer_id = item.data(Qt.ItemDataRole.UserRole)
        return next((layer for layer in self.layers if layer.id == layer_id), None)

    def update_layer_visibility(self, item: QListWidgetItem) -> None:
        layer_id = item.data(Qt.ItemDataRole.UserRole)
        layer = next((candidate for candidate in self.layers if candidate.id == layer_id), None)
        if layer is not None:
            layer.visible = item.checkState() is Qt.CheckState.Checked
            self.schedule_preview()
            self.schedule_estimate()

    def load_layer_controls(self) -> None:
        layer = self.current_layer()
        if layer is None:
            return
        self._loading_controls = True
        self.size_value.setText(str(round(layer.size)))
        self.size_unit.setCurrentIndex(1 if layer.size_unit is Unit.PIXELS else 0)
        self.opacity.setText(str(layer.opacity))
        self.horizontal_value.setText(str(round(layer.horizontal_inset)))
        self.horizontal_unit.setCurrentIndex({Unit.VISUAL: 0, Unit.PERCENT: 1, Unit.PIXELS: 2}[layer.horizontal_unit])
        self.vertical_value.setText(str(round(layer.vertical_inset)))
        self.vertical_unit.setCurrentIndex({Unit.VISUAL: 0, Unit.PERCENT: 1, Unit.PIXELS: 2}[layer.vertical_unit])
        self.rotation.setText(str(round(layer.rotation)))
        self._show_anchor(layer.anchor)
        self._loading_controls = False

    def store_layer_controls(self) -> None:
        if self._loading_controls:
            return
        layer = self.current_layer()
        if layer is None:
            return
        layer.size = self._number(self.size_value)
        layer.size_unit = Unit.PIXELS if self.size_unit.currentIndex() == 1 else Unit.PERCENT
        layer.opacity = self._number(self.opacity)
        layer.horizontal_inset = self._number(self.horizontal_value)
        layer.horizontal_unit = (Unit.VISUAL, Unit.PERCENT, Unit.PIXELS)[self.horizontal_unit.currentIndex()]
        layer.vertical_inset = self._number(self.vertical_value)
        layer.vertical_unit = (Unit.VISUAL, Unit.PERCENT, Unit.PIXELS)[self.vertical_unit.currentIndex()]
        layer.rotation = self._number(self.rotation)
        self.schedule_preview()
        self.schedule_estimate()

    @staticmethod
    def _number(field: QLineEdit) -> int:
        return int(field.text() or 0)

    def set_anchor(self, anchor: Anchor) -> None:
        layer = self.current_layer()
        if layer is None:
            return
        layer.anchor = anchor
        self._show_anchor(anchor)
        self.schedule_preview()
        self.schedule_estimate()

    def _show_anchor(self, anchor: Anchor) -> None:
        for button in self.anchor_buttons:
            selected = button.property("anchor") == anchor
            button.setChecked(selected)
            button.setText("●" if selected else "○")

    def sync_layer_order(self) -> None:
        order = [self.layer_list.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.layer_list.count())]
        self.layers.sort(key=lambda layer: order.index(layer.id))
        self.schedule_preview()
        self.schedule_estimate()

    def schedule_preview(self) -> None:
        self.preview_timer.start(30)

    def schedule_estimate(self) -> None:
        self.estimate_timer.start(1000)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self.schedule_preview()

    def refresh_preview(self) -> None:
        if self.source is None:
            return
        viewport = self.preview.size() * self.devicePixelRatioF()
        target_w, target_h = max(1, round(viewport.width())), max(1, round(viewport.height()))
        source_w, source_h = self.source.original_size
        scale = min(target_w / source_w, target_h / source_h, 1)
        preview_size = (max(1, round(source_w * scale)), max(1, round(source_h * scale)))
        preview_size = min(preview_size[0], self.source.image.width), min(preview_size[1], self.source.image.height)
        base = self.source.image.resize(preview_size, Image.Resampling.LANCZOS)
        preview_layers = self._scaled_layers(preview_size[0] / source_w)
        rendered = render(base, preview_layers)
        pixmap = self._pixmap(rendered)
        self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _scaled_layers(self, scale: float) -> list[WatermarkLayer]:
        return [
            replace(
                layer,
                size=layer.size * scale if layer.size_unit is Unit.PIXELS else layer.size,
                horizontal_inset=layer.horizontal_inset * scale if layer.horizontal_unit is Unit.PIXELS else layer.horizontal_inset,
                vertical_inset=layer.vertical_inset * scale if layer.vertical_unit is Unit.PIXELS else layer.vertical_inset,
            )
            for layer in self.layers
        ]

    def _pixmap(self, image: Image.Image) -> QPixmap:
        rgba = image.convert("RGBA")
        qimage = QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()
        return QPixmap.fromImage(qimage)

    def update_export_settings(self) -> None:
        self.quality_number.setText(str(self.quality.value()))
        self.resize_value.setEnabled(self.resize_mode.currentIndex() > 0)
        modes = [ResizeMode.NONE, ResizeMode.LONG_EDGE, ResizeMode.SHORT_EDGE, ResizeMode.SCALE]
        self.settings = ExportSettings(
            format=self.format.currentText(), quality=self.quality.value(), resize_mode=modes[self.resize_mode.currentIndex()],
            resize_value=float(self.resize_value.text() or 0), allow_upscale=self.allow_upscale.isChecked(), keep_exif=self.keep_exif.isChecked(), keep_icc=self.keep_icc.isChecked(), output_path=self.output_path.text().strip(),
        )
        self.schedule_preview()
        self.schedule_estimate()

    def resize_mode_changed(self) -> None:
        index = self.resize_mode.currentIndex()
        ratio = index == 3
        self.resize_value_label.setText(f"{self.t('约束数值')} ({'%' if ratio else 'px'})")
        self.resize_value.setText("" if index == 0 else "100" if ratio else "2048")
        self.update_export_settings()

    def select_output_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择导出路径", self.output_path.text())
        if path:
            self.output_path.setText(path)

    def update_estimate(self) -> None:
        if self.source is None:
            return
        try:
            source_size = self.source.original_size
            sample = render(self.source.image, self._scaled_layers(self.source.image.width / source_size[0]))
            output_size = export_size(source_size, self.settings)
            estimated = estimate_size(sample, replace(self.settings, resize_mode=ResizeMode.NONE))
            estimated *= (output_size[0] * output_size[1]) / max(1, sample.width * sample.height)
            current = self._bytes(estimated)
            self.current_estimate.setText(f"当前照片约 {current}")
            total = estimated * len(self.paths)
            self.batch_estimate.setText(f"本批次约 {self._bytes(total * 0.85)}–{self._bytes(total * 1.15)}")
        except Exception:  # noqa: BLE001
            self.current_estimate.setText("当前照片约 —")

    @staticmethod
    def _bytes(value: float) -> str:
        return f"{value / 1024 / 1024:.1f} MB"

    def save_watermark_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, self.t("保存水印预设"), f"{self.t('预设名称')}:")
        if accepted and name.strip():
            try:
                save_watermark_preset(name.strip(), self.layers)
            except OSError as exc:
                QMessageBox.warning(self, self.t("无法保存预设"), str(exc))
                return
            self.refresh_presets()
            self.watermark_preset.setCurrentText(name.strip())

    def save_export_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, self.t("保存导出预设"), f"{self.t('预设名称')}:")
        if accepted and name.strip():
            try:
                save_export_preset(name.strip(), self.settings)
            except OSError as exc:
                QMessageBox.warning(self, self.t("无法保存预设"), str(exc))
                return
            self.refresh_presets()
            self.export_preset.setCurrentText(name.strip())

    def refresh_presets(self) -> None:
        self.watermark_preset.blockSignals(True)
        self.export_preset.blockSignals(True)
        self.watermark_preset.clear(); self.watermark_preset.addItem(self.t("水印预设")); self.watermark_preset.addItems(load_watermark_presets())
        self.export_preset.clear(); self.export_preset.addItem(self.t("导出预设")); self.export_preset.addItems(load_export_presets())
        self.watermark_preset.blockSignals(False)
        self.export_preset.blockSignals(False)

    def apply_watermark_preset(self, name: str) -> None:
        presets = load_watermark_presets()
        if name not in presets:
            return
        preset_layers = presets[name]
        self.layers = []
        self.layer_list.clear()
        for layer in preset_layers:
            self.add_layer(layer)

    def apply_export_preset(self, name: str) -> None:
        presets = load_export_presets()
        if name not in presets:
            return
        self.settings = presets[name]
        self.format.setCurrentText(self.settings.format)
        self.quality.setValue(self.settings.quality)
        self.resize_mode.setCurrentIndex(list(ResizeMode).index(self.settings.resize_mode))
        self.resize_value.setText(str(round(self.settings.resize_value or (100 if self.settings.resize_mode is ResizeMode.SCALE else 2048))))
        self.allow_upscale.setChecked(self.settings.allow_upscale)
        self.keep_exif.setChecked(self.settings.keep_exif)
        self.keep_icc.setChecked(self.settings.keep_icc)
        self.output_path.setText(self.settings.output_path)

    def export_batch(self) -> None:
        if not self.paths:
            QMessageBox.information(self, "没有图片", "请先打开或拖入图片。")
            return
        destination = self.settings.output_path or QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not destination:
            return
        self.worker = ExportWorker(self.paths, Path(destination), list(self.layers), self.settings)
        self.worker.progressed.connect(lambda current, total, name: self.status.showMessage(f"导出 {current}/{total}: {name}"))
        self.worker.finished_batch.connect(self.export_finished)
        self.export_button.setEnabled(False)
        self.worker.start()

    def export_finished(self, complete: int, failures: list[str]) -> None:
        self.export_button.setEnabled(True)
        message = f"已导出 {complete} 张图片。"
        if failures:
            message += f"\n失败 {len(failures)} 张：\n" + "\n".join(failures[:3])
        QMessageBox.information(self, "导出完成", message)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About MeiWatermark",
            "MeiWatermark\nVersion 1.096\nGPL-3.0-or-later\n\n©2026 MeiStingray, Kicity Studio\nwww.kicity.com",
        )
