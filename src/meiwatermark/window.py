from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QEvent, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QDrag, QDragEnterEvent, QDropEvent, QIcon, QImage, QIntValidator, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
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
    QRadioButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStyle,
    QStyleFactory,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .export import EstimateWorker, ExportWorker
from .i18n import translate
from .model import Anchor, ExportSettings, LayerKind, ResizeMode, Unit, WatermarkLayer
from .presets import (
    load_presets,
    preset_exists,
    preset_directory,
    save_preset,
)
from .render import MAX_STAMP_SIZE, FontChoice, ImageSource, RenderLimitError, load_thumbnail, load_preview, render, scaled_layers, system_fonts


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


def trash_icon() -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(ACCENT), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawLine(7, 5, 17, 5)
    painter.drawLine(10, 3, 14, 3)
    painter.drawLine(9, 7, 10, 15)
    painter.drawLine(15, 7, 14, 15)
    painter.drawLine(10, 15, 14, 15)
    painter.drawLine(11, 8, 11, 13)
    painter.drawLine(13, 8, 13, 13)
    painter.end()
    return QIcon(pixmap)


class LayerList(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.drag_pixmap = QPixmap()
        self.drag_hotspot = None

    def set_drag_preview(self, pixmap: QPixmap, hotspot) -> None:  # type: ignore[no-untyped-def]
        self.drag_pixmap, self.drag_hotspot = pixmap, hotspot

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        index = self.currentIndex()
        if not index.isValid():
            return
        drag = QDrag(self)
        drag.setMimeData(self.model().mimeData([index]))
        if not self.drag_pixmap.isNull() and self.drag_hotspot is not None:
            drag.setPixmap(self.drag_pixmap)
            drag.setHotSpot(self.drag_hotspot)
        drag.exec(supported_actions, Qt.DropAction.MoveAction)
        self.drag_pixmap = QPixmap()
        self.drag_hotspot = None


class LayerRow(QWidget):
    def __init__(self, owner: LayerList, item: QListWidgetItem, layer: WatermarkLayer, edit, remove, name_text: str, edit_tooltip: str, remove_tooltip: str) -> None:  # type: ignore[no-untyped-def]
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
        if layer.kind is LayerKind.TEXT or layer.tiled:
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
        drag.setObjectName("dragLayer")
        drag.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(drag, 0, Qt.AlignmentFlag.AlignVCenter)
        button = QToolButton()
        button.setObjectName("deleteLayer")
        button.setIcon(trash_icon())
        button.setIconSize(QSize(20, 20))
        button.setFixedSize(28, 28)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(remove_tooltip)
        button.clicked.connect(remove)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.owner.setCurrentItem(self.item)
        self.drag_start = event.position()
        self.owner.set_drag_preview(self.grab(), self.drag_start.toPoint())
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.drag_start and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position() - self.drag_start).manhattanLength() >= 4:
                self.drag_start = None
                self.owner.startDrag(Qt.DropAction.MoveAction)
        event.accept()


class ThumbnailDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:  # type: ignore[no-untyped-def]
        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, clean_option, index)


class LayerDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:  # type: ignore[no-untyped-def]
        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, clean_option, index)


class ResetSlider(QSlider):
    def __init__(self, minimum: int, maximum: int, value: int, reset_value: int = 0) -> None:
        super().__init__(Qt.Orientation.Horizontal)
        self.reset_value = reset_value
        self.setRange(minimum, maximum)
        self.setValue(value)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.setValue(self.reset_value)
        event.accept()


class FontLoader(QThread):
    ready = Signal(object)

    def __init__(self, language: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.language = language

    def run(self) -> None:
        self.ready.emit(system_fonts(self.language))


class ImageLoader(QThread):
    ready = Signal(object, object)
    failed = Signal(object, str)

    def __init__(self, path: Path, max_size: tuple[int, int], preview: bool, parent: QWidget) -> None:
        super().__init__(parent)
        self.path, self.max_size, self.preview = path, max_size, preview
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            image = load_preview(self.path, self.max_size) if self.preview else load_thumbnail(self.path, self.max_size)
            if not self._cancelled:
                self.ready.emit(self.path, image)
        except Exception as exc:  # noqa: BLE001
            if not self._cancelled:
                self.failed.emit(self.path, str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MeiWatermark")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "app-icon.png")))
        self.resize(1280, 800)
        self.setMinimumSize(960, 620)
        self.setAcceptDrops(True)
        self.language = "zh"
        self.paths: list[Path] = []
        self.layers: list[WatermarkLayer] = []
        self.source = None
        self.source_path: Path | None = None
        self.settings = ExportSettings()
        self.worker: ExportWorker | None = None
        self.estimate_worker: EstimateWorker | None = None
        self._estimate_active_keys: set[tuple] = set()
        self._estimate_cache: dict[tuple, float | None] = {}
        self._estimate_pending = False
        self.font_loaders: list[FontLoader] = []
        self.preview_loader: ImageLoader | None = None
        self.preview_pending: Path | None = None
        self.thumbnail_loader: ImageLoader | None = None
        self.thumbnail_queue: list[Path] = []
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
        settings = self.settings
        self.thumbnail_queue.clear()
        if self.thumbnail_loader is not None:
            self.thumbnail_loader.cancel()
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
        self.format.setCurrentText(settings.format)
        self.quality.setValue(settings.quality)
        self.resize_mode.setCurrentIndex(list(ResizeMode).index(settings.resize_mode))
        self.resize_value.setText(str(round(settings.resize_value)) if settings.resize_value else "")
        self.allow_upscale.setChecked(not settings.allow_upscale)
        self.keep_exif.setChecked(settings.keep_exif)
        self.keep_icc.setChecked(settings.keep_icc)
        self.output_path.setText(settings.output_path)
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
        tiled_button = QPushButton(self.t("添加全屏水印"))
        tiled_button.clicked.connect(self.add_tiled_layer)
        row.addWidget(tiled_button)
        row.addStretch()
        self.preset = QComboBox()
        self.preset.addItem(self.t("预设"))
        self.preset.currentTextChanged.connect(self.apply_preset)
        row.addWidget(self.preset)
        save = QPushButton(self.t("保存"))
        save.setObjectName("presetSave")
        save.clicked.connect(self.save_preset)
        row.addWidget(save)
        manage = QPushButton(self.t("管理"))
        manage.clicked.connect(self.open_preset_directory)
        row.addWidget(manage)
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
        self.layer_list = LayerList()
        self.layer_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.layer_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.layer_list.setItemDelegate(LayerDelegate(self.layer_list))
        self.layer_list.currentItemChanged.connect(lambda *_: self.load_layer_controls())
        self.layer_list.itemDoubleClicked.connect(self.edit_layer)
        self.layer_list.itemChanged.connect(self.update_layer_visibility)
        self.layer_list.model().rowsMoved.connect(lambda *_: self.sync_layer_order())
        layout.addWidget(self.layer_list, 1)
        layout.addWidget(self._line())
        layout.addWidget(self._heading(self.t("选中图层属性")))
        controls = QFrame()
        controls.setObjectName("propertyPanel")
        properties = QVBoxLayout(controls)
        properties.setContentsMargins(7, 7, 7, 7)
        properties.setSpacing(8)
        self.size_value, self.size_unit = self._number_unit(24, [self.t("百分比"), "px"], 1)
        properties.addWidget(self._property_row(self.t("大小"), self._stepper(self.size_value, 1, MAX_STAMP_SIZE), self.size_unit))
        self.horizontal_value, self.horizontal_unit = self._number_unit(2, [self.t("视觉比例"), self.t("百分比"), "px"], -100000)
        self.horizontal_row = self._property_row(self.t("水平内嵌"), self._stepper(self.horizontal_value, -100000, 100000), self.horizontal_unit)
        properties.addWidget(self.horizontal_row)
        self.vertical_value, self.vertical_unit = self._number_unit(2, [self.t("视觉比例"), self.t("百分比"), "px"], -100000)
        self.vertical_row = self._property_row(self.t("垂直内嵌"), self._stepper(self.vertical_value, -100000, 100000), self.vertical_unit)
        properties.addWidget(self.vertical_row)
        self.opacity, self.opacity_number = self._slider_editor(0, 100, 80, 80)
        properties.addWidget(self._property_row(self.t("透明度"), self._slider_widget(self.opacity, self.opacity_number)))
        self.rotation, self.rotation_number = self._slider_editor(-180, 180, 0)
        properties.addWidget(self._property_row(self.t("旋转"), self._slider_widget(self.rotation, self.rotation_number)))
        layout.addWidget(controls)
        self.anchor_heading = self._heading(self.t("九宫格定位"))
        layout.addWidget(self.anchor_heading)
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
        self.anchor_grid = grid_widget
        layout.addWidget(grid_widget)
        for widget in (self.size_value, self.size_unit, self.horizontal_value, self.horizontal_unit, self.vertical_value, self.vertical_unit):
            if isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(lambda *_: self.store_layer_controls())
            else:
                widget.textChanged.connect(lambda *_: self.store_layer_controls())
        for slider in (self.opacity, self.rotation):
            slider.valueChanged.connect(self.store_layer_controls)
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
        clear = QPushButton(self.t("清空列表"))
        clear.clicked.connect(self.clear_photo_list)
        heading.addWidget(clear)
        layout.addLayout(heading)
        self.preview = QLabel(self.t("拖拽图片到窗口任意位置即可导入"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("preview")
        self.preview.setMinimumSize(420, 360)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self._line())
        self.thumbnails = QListWidget()
        self.thumbnails.setItemDelegate(ThumbnailDelegate(self.thumbnails))
        self.thumbnails.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbnails.setFlow(QListWidget.Flow.LeftToRight)
        self.thumbnails.setWrapping(False)
        self.thumbnails.setIconSize(QSize(94, 70))
        self.thumbnails.setGridSize(QSize(108, 90))
        self.thumbnails.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.thumbnails.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.thumbnails.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbnails.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.thumbnails.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbnails.setFixedHeight(108)
        self.thumbnails.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumbnails.customContextMenuRequested.connect(self.show_thumbnail_menu)
        self.thumbnails.currentRowChanged.connect(self.select_photo)
        self.thumbnails.installEventFilter(self)
        self.thumbnails.viewport().installEventFilter(self)
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
        form.setVerticalSpacing(12)
        self.format = QComboBox()
        self.format.addItems(["JPEG", "PNG", "WEBP"])
        form.addRow(self.t("格式"), self.format)
        self.quality, self.quality_number = self._slider_editor(1, 100, 100, 100)
        form.addRow(self.t("质量"), self._slider_widget(self.quality, self.quality_number))
        self.resize_mode = QComboBox()
        self.resize_mode.addItems([self.t(value) for value in ("不约束", "最长边", "最短边", "比例")])
        form.addRow(self.t("尺寸约束"), self.resize_mode)
        self.resize_value = QLineEdit()
        self.resize_value.setValidator(QIntValidator(1, 100000, self))
        self.resize_value.setEnabled(False)
        self.resize_value_label = QLabel(f"{self.t('约束数值')} (px)")
        form.addRow(self.resize_value_label, self.resize_value)
        self.allow_upscale = QCheckBox(self.t("不放大"))
        self.allow_upscale.setChecked(True)
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
        estimate_heading = self._heading(self.t("预计文件大小"))
        estimate_heading.setIndent(0)
        self.current_estimate = QLabel(self.t("当前照片约 —"))
        self.current_estimate.setIndent(0)
        estimate_layout = QVBoxLayout()
        estimate_layout.setContentsMargins(0, 0, 0, 0)
        estimate_layout.setSpacing(4)
        estimate_layout.addWidget(estimate_heading)
        estimate_layout.addWidget(self.current_estimate)
        layout.addLayout(estimate_layout)
        self.export_button = QPushButton(self.t("导出"))
        self.export_button.setObjectName("primary")
        self.export_button.setEnabled(self.worker is None or not self.worker.isRunning())
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
    def _slider_editor(minimum: int, maximum: int, value: int, reset_value: int = 0) -> tuple[QSlider, QLineEdit]:
        slider = ResetSlider(minimum, maximum, value, reset_value)
        number = QLineEdit(str(value))
        number.setValidator(QIntValidator(minimum, maximum, number))
        number.setFixedWidth(42)
        number.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider.valueChanged.connect(lambda current: number.setText(str(current)))

        def apply_number() -> None:
            try:
                slider.setValue(max(minimum, min(maximum, int(number.text()))))
            except ValueError:
                number.setText(str(slider.value()))

        number.editingFinished.connect(apply_number)
        return slider, number

    @staticmethod
    def _slider_widget(slider: QSlider, number: QLineEdit) -> QWidget:
        widget = QWidget()
        widget.setObjectName("sliderEditor")
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        row.addWidget(slider, 1)
        row.addWidget(number)
        return widget

    @staticmethod
    def _property_row(label: str, editor: QWidget, unit: QComboBox | None = None) -> QWidget:
        widget = QWidget()
        widget.setObjectName("propertyRow")
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        name = QLabel(label)
        name.setFixedWidth(52)
        row.addWidget(name)
        row.addWidget(editor, 1)
        if unit is not None:
            unit.setFixedWidth(74)
            row.addWidget(unit)
        else:
            row.addStretch()
        widget.setFixedHeight(30)
        return widget

    def _apply_style(self) -> None:
        arrow = (Path(__file__).parent / "assets" / "down-arrow.svg").resolve().as_posix()
        self.setStyleSheet(f"""
            QWidget {{ font-size: 9pt; color: #202124; }}
            QMainWindow, QWidget {{ background: #f5f6f8; }}
            QMenuBar {{ background: #ffffff; border-bottom: 1px solid #e3e5e8; padding: 1px 3px; }}
            QMenuBar::item {{ padding: 4px 8px; background: transparent; }}
            QMenuBar::item:selected {{ background: #eceef2; }}
            QPushButton, QComboBox, QLineEdit {{ min-height: 24px; border: 1px solid #d7dbe1; border-radius: 2px; padding: 1px 7px; background: #fff; }}
            QPushButton:hover, QComboBox:hover {{ border-color: {ACCENT}; }}
            QComboBox:on {{ border-color: {ACCENT}; background: #fff; }}
            QComboBox::drop-down {{ width: 18px; border: none; background: transparent; }}
            QComboBox::drop-down:on {{ width: 18px; border: none; background: transparent; }}
            QComboBox::down-arrow {{ image: url("{arrow}"); width: 8px; height: 5px; }}
            QComboBox::down-arrow:on {{ image: url("{arrow}"); width: 8px; height: 5px; }}
            QComboBox QAbstractItemView {{ background: #fff; border: 1px solid #d7dbe1; color: #202124; outline: 0; selection-background-color: #f5dce9; selection-color: #202124; }}
            QComboBox QAbstractItemView::item {{ background: #fff; padding: 2px 7px; }}
            QComboBox QAbstractItemView::item:selected {{ background: #f5dce9; color: #202124; }}
            QPushButton#primary {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT}; font-weight: 600; }}
            QPushButton#primary:pressed {{ background: #760743; border-color: #5b0635; padding: 2px 7px 0 7px; }}
            QPushButton#presetSave {{ color: {ACCENT}; border-color: {ACCENT}; font-weight: 600; }}
            QLabel#heading {{ font-size: 10pt; font-weight: 600; margin: 2px 0; }}
            QLabel#preview {{ font-size: 12pt; background: #262a30; border: 1px solid #363b43; color: #c8ccd2; }}
            QWidget#sidePanel {{ background: #ffffff; }}
            QWidget#sidePanel QLabel, QWidget#sidePanel QCheckBox {{ background: transparent; }}
            QListWidget {{ background: #fff; border: 1px solid #d9dde3; border-radius: 0; padding: 2px; }}
            QListWidget::item {{ padding: 5px; border-radius: 0; }}
            QListWidget::item:selected {{ background: #f5dce9; border: 1px solid {ACCENT}; color: #202124; }}
            QListWidget::item:selected:active, QListWidget::item:selected:!active {{ color: #202124; }}
            QListWidget::item:focus {{ outline: none; }}
            QToolButton:checked {{ color: {ACCENT}; }}
            QToolButton#editLayer, QToolButton#deleteLayer {{ border: none; background: transparent; padding: 0 0 4px 0; }}
            QToolButton#editLayer:hover {{ background: #f5dce9; border-radius: 4px; }}
            QToolButton#deleteLayer:hover, QToolButton#deleteLayer:pressed {{ background: transparent; }}
            QLabel#dragLayer {{ color: {ACCENT}; }}
            QToolButton#step {{ min-width: 20px; border: 1px solid #d7dbe1; border-radius: 2px; background: #fff; font-weight: 600; }}
            QToolButton#step:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
            QToolButton#anchor {{ border: none; background: transparent; border-radius: 17px; font-size: 16pt; color: #7b818a; }}
            QToolButton#anchor:checked {{ border: none; background: #f9e3ef; color: {ACCENT}; }}
            QFrame#propertyPanel {{ background: #ffffff; border: 1px solid #dfe2e7; border-radius: 3px; }}
            QFrame#propertyPanel QLabel, QWidget#propertyRow, QWidget#stepper, QWidget#sliderEditor, QWidget#anchorGrid {{ background: transparent; }}
            QSlider, QSlider::groove:horizontal {{ border: none; background: transparent; }}
            QSlider::groove:horizontal {{ height: 3px; margin: 0; }}
            QSlider::add-page:horizontal, QSlider::sub-page:horizontal {{ height: 3px; margin: 0; border: none; }}
            QSlider::add-page:horizontal {{ background: transparent; }}
            QSlider::sub-page:horizontal {{ background: {ACCENT}; }}
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
        files, _ = QFileDialog.getOpenFileNames(self, self.t("打开图片"), "", IMAGE_FILTER)
        self.add_paths([Path(file) for file in files])

    def add_paths(self, paths: list[Path]) -> None:
        supported = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
        added = [path for path in paths if path.is_file() and path.suffix.lower() in supported and path not in self.paths]
        if not added:
            return
        self.paths.extend(added)
        last_item = None
        for path in added:
            item = QListWidgetItem(display_image_name(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.thumbnails.addItem(item)
            self.thumbnail_queue.append(path)
            last_item = item
        if last_item is not None:
            self.thumbnails.setCurrentItem(last_item)
            self.thumbnails.scrollToItem(last_item, QAbstractItemView.ScrollHint.PositionAtCenter)
        self.status.showMessage(self.t("已导入 {count} 张图片").format(count=len(added)), 3000)
        self._load_next_thumbnail()

    def _load_next_thumbnail(self) -> None:
        if self.thumbnail_loader is not None or not self.thumbnail_queue:
            return
        worker = ImageLoader(self.thumbnail_queue.pop(0), (240, 180), False, self)
        self.thumbnail_loader = worker
        worker.ready.connect(self._thumbnail_loaded)
        worker.finished.connect(lambda current=worker: self._thumbnail_finished(current))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _thumbnail_loaded(self, path: Path, image: Image.Image) -> None:
        for row in range(self.thumbnails.count()):
            item = self.thumbnails.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                item.setIcon(self._pixmap(image))
                return

    def _thumbnail_finished(self, worker: ImageLoader) -> None:
        if self.thumbnail_loader is worker:
            self.thumbnail_loader = None
            self._load_next_thumbnail()

    def select_photo(self, row: int) -> None:
        if row < 0:
            return
        path = self.thumbnails.item(row).data(Qt.ItemDataRole.UserRole)
        self._refresh_estimate_labels()
        self._load_preview(path)

    def _load_preview(self, path: Path) -> None:
        if self.preview_loader is not None:
            if self.preview_loader.path == path and self.preview_pending is None:
                return
            self.preview_loader.cancel()
            self.preview_pending = path
            return
        worker = ImageLoader(path, (1200, 1200), True, self)
        self.preview_loader = worker
        worker.ready.connect(self._preview_loaded)
        worker.failed.connect(self._preview_failed)
        worker.finished.connect(lambda current=worker: self._preview_finished(current))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _preview_loaded(self, path: Path, source: ImageSource) -> None:
        if self._selected_path() == path:
            self.source = source
            self.source_path = path
            self.schedule_preview()
            self.schedule_estimate()

    def _preview_failed(self, path: Path, error: str) -> None:
        if self._selected_path() == path:
            self.source = None
            self.source_path = None
            self.preview.setText(self.t("拖拽图片到窗口任意位置即可导入"))
            self.preview.setPixmap(QPixmap())
            self._refresh_estimate_labels()
            QMessageBox.warning(self, self.t("无法读取图片"), error)

    def _preview_finished(self, worker: ImageLoader) -> None:
        if self.preview_loader is not worker:
            return
        self.preview_loader = None
        path, self.preview_pending = self.preview_pending, None
        if path is not None and self._selected_path() == path:
            self._load_preview(path)

    def remove_selected_photo(self) -> None:
        row = self.thumbnails.currentRow()
        if row < 0:
            return
        item = self.thumbnails.takeItem(row)
        path = item.data(Qt.ItemDataRole.UserRole)
        self.paths.remove(path)
        self.thumbnail_queue = [queued for queued in self.thumbnail_queue if queued != path]
        if self.thumbnail_loader is not None and self.thumbnail_loader.path == path:
            self.thumbnail_loader.cancel()
        if self.thumbnails.count():
            self.thumbnails.setCurrentRow(min(row, self.thumbnails.count() - 1))
        else:
            self.source = None
            self.source_path = None
            self.preview.setText(self.t("拖拽图片到窗口任意位置即可导入"))
            self.preview.setPixmap(QPixmap())
            self.current_estimate.setText(self.t("当前照片约 —"))

    def eventFilter(self, watched, event):  # type: ignore[no-untyped-def]
        if watched in (self.thumbnails, self.thumbnails.viewport()) and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Delete:
            self.remove_selected_photo()
            return True
        return super().eventFilter(watched, event)

    def clear_photo_list(self) -> None:
        self.paths.clear()
        self.thumbnail_queue.clear()
        if self.thumbnail_loader is not None:
            self.thumbnail_loader.cancel()
        self.preview_pending = None
        if self.preview_loader is not None:
            self.preview_loader.cancel()
        self.thumbnails.clear()
        self.source = None
        self.source_path = None
        self.preview.setText(self.t("拖拽图片到窗口任意位置即可导入"))
        self.preview.setPixmap(QPixmap())
        self.current_estimate.setText(self.t("当前照片约 —"))

    def show_thumbnail_menu(self, position) -> None:  # type: ignore[no-untyped-def]
        item = self.thumbnails.itemAt(position)
        if item is None:
            return
        self.thumbnails.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction(self.t("从列表移除"), self.remove_selected_photo)
        menu.exec(self.thumbnails.viewport().mapToGlobal(position))

    def add_image_layer(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.t("选择水印图片"), "", IMAGE_FILTER)
        if path:
            self.add_layer(WatermarkLayer(LayerKind.IMAGE, "图片水印", image_path=path))

    def add_text_layer(self) -> None:
        layer = WatermarkLayer(LayerKind.TEXT, "文字水印", text="MeiStingray")
        if self.edit_text_dialog(layer):
            self.add_layer(layer)

    def add_tiled_layer(self) -> None:
        layer = WatermarkLayer(LayerKind.TEXT, "全屏文字", text="MeiStingray", size=12, opacity=15, rotation=-30, tiled=True)
        if self.edit_tiled_dialog(layer, select_mode=False):
            self.add_layer(layer)

    def add_layer(self, layer: WatermarkLayer) -> None:
        if layer.size_unit is Unit.PIXELS:
            layer.size = min(layer.size, MAX_STAMP_SIZE)
        self.layers.append(layer)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, layer.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked)
        item.setSizeHint(QSize(0, 28))
        self.layer_list.addItem(item)
        self.layer_list.setItemWidget(item, LayerRow(self.layer_list, item, layer, lambda: self.edit_layer(item), lambda: self.remove_layer(item), self._layer_label(layer), self.t("编辑全屏水印") if layer.tiled else self.t("编辑文字水印"), self.t("删除图层")))
        self.layer_list.setCurrentItem(item)
        self.schedule_preview()
        self.schedule_estimate()

    def remove_layer(self, item: QListWidgetItem) -> None:
        row = self.layer_list.row(item)
        if row < 0:
            return
        layer_id = item.data(Qt.ItemDataRole.UserRole)
        self.layer_list.takeItem(row)
        self.layers = [layer for layer in self.layers if layer.id != layer_id]
        if self.layer_list.count():
            self.layer_list.setCurrentRow(min(row, self.layer_list.count() - 1))
        self.schedule_preview()
        self.schedule_estimate()

    def _layer_label(self, layer: WatermarkLayer) -> str:
        if layer.tiled:
            content = layer.text if layer.kind is LayerKind.TEXT else Path(layer.image_path or "").name
            return f"{self.t(layer.name)}：{content}"
        return layer.text if layer.kind is LayerKind.TEXT else self.t(layer.name)

    def _refresh_layer_label(self, item: QListWidgetItem, layer: WatermarkLayer) -> None:
        row = self.layer_list.itemWidget(item)
        if isinstance(row, LayerRow):
            row.name_label.setText(self._layer_label(layer))

    def edit_layer(self, item: QListWidgetItem) -> None:
        layer_id = item.data(Qt.ItemDataRole.UserRole)
        layer = next((candidate for candidate in self.layers if candidate.id == layer_id), None)
        if layer is None:
            return
        changed = self.edit_tiled_dialog(layer) if layer.tiled else self.edit_text_dialog(layer) if layer.kind is LayerKind.TEXT else False
        if changed:
            self._refresh_layer_label(item, layer)
            self.schedule_preview()
            self.schedule_estimate()

    def edit_text_layer(self, item: QListWidgetItem) -> None:
        self.edit_layer(item)

    def edit_tiled_dialog(self, layer: WatermarkLayer, select_mode: bool = True) -> bool:
        draft = deepcopy(layer)
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("全屏水印"))
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, 22)
        grid.setColumnStretch(3, 1)
        image_mode = QRadioButton()
        text_mode = QRadioButton()
        modes = QButtonGroup(dialog)
        radio_style = QStyleFactory.create("Fusion")
        if radio_style is not None:
            radio_style.setParent(dialog)
        for button, name in ((image_mode, "tileImageMode"), (text_mode, "tileTextMode")):
            button.setObjectName(name)
            modes.addButton(button)
            if radio_style is not None:
                button.setStyle(radio_style)
            button.setFixedSize(22, 26)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        selected_kind = [draft.kind if select_mode else None]
        image_button = QPushButton(self.t("选择图片"))
        image_button.setObjectName("tileImage")
        image_name = QLabel(Path(draft.image_path).name if draft.image_path else self.t("未选择"))
        image_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_button = QPushButton(self.t("编辑文字"))
        text_button.setObjectName("tileText")
        text_name = QLabel(draft.text)
        text_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        image_label = QLabel(self.t("使用图片"))
        image_label.setObjectName("tileImageLabel")
        text_label = QLabel(self.t("使用文字"))
        text_label.setObjectName("tileTextLabel")
        grid.addWidget(image_mode, 0, 0, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(image_label, 0, 1)
        grid.addWidget(image_button, 0, 2)
        grid.addWidget(image_name, 0, 3)
        grid.addWidget(text_mode, 1, 0, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(text_label, 1, 1)
        grid.addWidget(text_button, 1, 2)
        grid.addWidget(text_name, 1, 3)

        def select(kind: LayerKind) -> None:
            selected_kind[0] = kind
            for button, selected in ((image_mode, kind is LayerKind.IMAGE), (text_mode, kind is LayerKind.TEXT)):
                button.setChecked(selected)

        def choose_image() -> None:
            path, _ = QFileDialog.getOpenFileName(dialog, self.t("选择图片"), "", IMAGE_FILTER)
            if path:
                draft.image_path = path
                image_name.setText(Path(path).name)
                select(LayerKind.IMAGE)

        def edit_text() -> None:
            select(LayerKind.TEXT)
            if self.edit_text_dialog(draft):
                text_name.setText(draft.text)

        image_mode.clicked.connect(lambda: select(LayerKind.IMAGE))
        text_mode.clicked.connect(lambda: select(LayerKind.TEXT))
        image_button.clicked.connect(choose_image)
        text_button.clicked.connect(edit_text)
        if selected_kind[0] is not None:
            select(selected_kind[0])
        gap = QLineEdit(str(round(draft.tile_gap)))
        gap.setObjectName("tileGap")
        gap.setValidator(QIntValidator(0, 100000, dialog))
        gap.setFixedWidth(58)
        gap_editor = QWidget()
        gap_layout = QHBoxLayout(gap_editor)
        gap_layout.setContentsMargins(0, 0, 0, 0)
        gap_layout.setSpacing(5)
        gap_layout.addWidget(gap)
        gap_layout.addWidget(QLabel("%"))
        gap_label = QLabel(self.t("间距"))
        gap_label.setObjectName("tileGapLabel")
        grid.addWidget(gap_label, 2, 1)
        grid.addWidget(gap_editor, 2, 2)
        stagger = QCheckBox()
        stagger.setObjectName("tileStagger")
        stagger.setFixedSize(22, 26)
        stagger.setChecked(draft.tile_stagger)
        grid.addWidget(stagger, 3, 0, Qt.AlignmentFlag.AlignCenter)
        stagger_label = QLabel(self.t("错列"))
        stagger_label.setObjectName("tileStaggerLabel")
        grid.addWidget(stagger_label, 3, 1)
        layout.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        def accept() -> None:
            if selected_kind[0] is None:
                QMessageBox.warning(dialog, self.t("全屏水印"), self.t("请选择图片或文字"))
                return
            if selected_kind[0] is LayerKind.IMAGE and not draft.image_path:
                QMessageBox.warning(dialog, self.t("全屏水印"), self.t("请选择图片"))
                return
            dialog.accept()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        draft.kind = selected_kind[0]
        draft.name = "全屏图片" if draft.kind is LayerKind.IMAGE else "全屏文字"
        draft.tiled = True
        draft.tile_gap = self._number(gap)
        draft.tile_stagger = stagger.isChecked()
        for attribute in fields(WatermarkLayer):
            setattr(layer, attribute.name, getattr(draft, attribute.name))
        return True

    def edit_text_dialog(self, layer: WatermarkLayer) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("文字水印"))
        dialog.setMinimumWidth(420)
        form = QFormLayout(dialog)
        text = QLineEdit(layer.text)
        form.addRow(self.t("文字"), text)
        font = QComboBox()
        font.setMinimumWidth(300)
        font.addItem(self.t("系统默认"), None)
        font.setEnabled(False)
        weight = QComboBox()
        weight.setMinimumWidth(130)
        weight.setEnabled(False)

        def populate_fonts(choices: list[FontChoice]) -> None:
            selected = (layer.font_path, layer.font_index, tuple(layer.font_variation))
            families: dict[str, list[FontChoice]] = {}
            for choice in choices:
                families.setdefault(choice.family, []).append(choice)
            font.clear()
            font.addItem(self.t("系统默认"), None)
            for family in sorted(families, key=lambda name: (not any(ord(character) > 127 for character in name), name.casefold())):
                font.addItem(family, families[family])

            def populate_weights() -> None:
                weight.clear()
                choices_for_family = font.currentData()
                if not choices_for_family:
                    weight.setEnabled(False)
                    return
                unique = {(choice.style, choice.path, choice.index, choice.variation): choice for choice in choices_for_family}
                for choice in sorted(unique.values(), key=lambda item: item.style.casefold()):
                    weight.addItem(choice.style, choice)
                index = next((position for position in range(weight.count()) if (choice := weight.itemData(position)) and (choice.path, choice.index, choice.variation) == selected), 0)
                weight.setCurrentIndex(index)
                weight.setEnabled(True)

            index = next((position for position in range(1, font.count()) if any((choice.path, choice.index, choice.variation) == selected for choice in font.itemData(position))), 0)
            font.setCurrentIndex(index)
            font.currentIndexChanged.connect(populate_weights)
            font.setEnabled(True)
            populate_weights()

        loader = FontLoader(self.language, self)
        loader.ready.connect(populate_fonts)
        loader.finished.connect(lambda: self.font_loaders.remove(loader) if loader in self.font_loaders else None)
        loader.finished.connect(loader.deleteLater)
        self.font_loaders.append(loader)
        loader.start()
        form.addRow(self.t("字体"), font)
        form.addRow(self.t("字重"), weight)
        text_color = QPushButton()
        stroke_color = QPushButton()
        text_none = QCheckBox(self.t("无颜色"))
        stroke_none = QCheckBox(self.t("无颜色"))
        stroke_width = QLineEdit(str(layer.stroke_width))
        stroke_width.setValidator(QIntValidator(0, 100, dialog))

        def set_color(button: QPushButton, title: str) -> None:
            color = QColorDialog.getColor(button.property("color"), dialog, title)
            if color.isValid():
                button.setProperty("color", color)
                button.setStyleSheet(f"background: {color.name()};")

        for button, color, toggle, title, fallback in ((text_color, layer.color, text_none, "文字颜色", (255, 255, 255)), (stroke_color, layer.stroke_color, stroke_none, "边框颜色", (0, 0, 0))):
            color = color or fallback
            button.setProperty("color", QColor(*color))
            button.setStyleSheet(f"background: rgb({color[0]}, {color[1]}, {color[2]});")
            button.clicked.connect(lambda _, target=button, label=title: set_color(target, self.t(label)))
            toggle.setChecked(color == fallback and ((button is text_color and layer.color is None) or (button is stroke_color and layer.stroke_color is None)))
            toggle.toggled.connect(lambda checked, target=button: target.setEnabled(not checked))
            button.setEnabled(not toggle.isChecked())
        for label, button, toggle in ((self.t("文字颜色"), text_color, text_none), (self.t("边框颜色"), stroke_color, stroke_none)):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(button)
            layout.addWidget(toggle)
            form.addRow(label, row)
        form.addRow(self.t("边框宽度"), stroke_width)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or not text.text().strip():
            return False
        layer.text = text.text().strip()
        choice = weight.currentData()
        layer.font_path = choice.path if isinstance(choice, FontChoice) else None
        layer.font_index = choice.index if isinstance(choice, FontChoice) else 0
        layer.font_variation = list(choice.variation) if isinstance(choice, FontChoice) else []
        layer.color = None if text_none.isChecked() else tuple(text_color.property("color").getRgb()[:3])
        layer.stroke_color = None if stroke_none.isChecked() else tuple(stroke_color.property("color").getRgb()[:3])
        layer.stroke_width = int(stroke_width.text() or 0)
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
        if layer.size_unit is Unit.PIXELS:
            layer.size = min(layer.size, MAX_STAMP_SIZE)
        self.size_value.setText(str(round(layer.size)))
        self.size_unit.setCurrentIndex(0 if layer.size_unit is Unit.PERCENT else 1)
        self.opacity.setValue(layer.opacity)
        self.opacity_number.setText(str(layer.opacity))
        self.horizontal_value.setText(str(round(layer.horizontal_inset)))
        self.horizontal_unit.setCurrentIndex({Unit.VISUAL: 0, Unit.PERCENT: 1, Unit.PIXELS: 2}[layer.horizontal_unit])
        self.vertical_value.setText(str(round(layer.vertical_inset)))
        self.vertical_unit.setCurrentIndex({Unit.VISUAL: 0, Unit.PERCENT: 1, Unit.PIXELS: 2}[layer.vertical_unit])
        self.rotation.setValue(round(layer.rotation))
        self.rotation_number.setText(str(round(layer.rotation)))
        self._show_anchor(layer.anchor)
        self.horizontal_row.setEnabled(not layer.tiled)
        self.vertical_row.setEnabled(not layer.tiled)
        self.anchor_heading.setEnabled(not layer.tiled)
        self.anchor_grid.setEnabled(not layer.tiled)
        self._loading_controls = False

    def store_layer_controls(self) -> None:
        if self._loading_controls:
            return
        layer = self.current_layer()
        if layer is None:
            return
        layer.size_unit = (Unit.PERCENT, Unit.PIXELS)[self.size_unit.currentIndex()]
        layer.size = self._number(self.size_value)
        if layer.size_unit is Unit.PIXELS and layer.size > MAX_STAMP_SIZE:
            layer.size = MAX_STAMP_SIZE
            self.size_value.setText(str(MAX_STAMP_SIZE))
        self.opacity_number.setText(str(self.opacity.value()))
        layer.opacity = self.opacity.value()
        layer.horizontal_inset = self._number(self.horizontal_value)
        layer.horizontal_unit = (Unit.VISUAL, Unit.PERCENT, Unit.PIXELS)[self.horizontal_unit.currentIndex()]
        layer.vertical_inset = self._number(self.vertical_value)
        layer.vertical_unit = (Unit.VISUAL, Unit.PERCENT, Unit.PIXELS)[self.vertical_unit.currentIndex()]
        self.rotation_number.setText(str(self.rotation.value()))
        layer.rotation = self.rotation.value()
        self.schedule_preview()
        self.schedule_estimate()

    @staticmethod
    def _number(field: QLineEdit) -> int:
        try:
            return int(field.text())
        except ValueError:
            return 0

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
        self._refresh_estimate_labels()
        selected = self._selected_path()
        if self.source is None or selected is None or self.source_path != selected or self._estimate_key(selected) in self._estimate_cache:
            return
        self.estimate_timer.start(1000)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self.schedule_preview()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        workers = [worker for worker in (self.worker, self.estimate_worker, self.preview_loader, self.thumbnail_loader) if worker is not None]
        workers.extend(self.font_loaders)
        active = [worker for worker in workers if worker.isRunning()]
        if active:
            for worker in active:
                if hasattr(worker, "cancel"):
                    worker.cancel()
            event.ignore()
            QTimer.singleShot(50, self.close)
            return
        super().closeEvent(event)

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
        preview_layers = scaled_layers(self.layers, preview_size[0] / source_w)
        try:
            rendered = render(base, preview_layers)
        except RenderLimitError:
            self.status.showMessage(self.t("水印设置超过限制"), 3000)
            rendered = base
        pixmap = self._pixmap(rendered)
        self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

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
            resize_value=float(self.resize_value.text() or 0), allow_upscale=not self.allow_upscale.isChecked(), keep_exif=self.keep_exif.isChecked(), keep_icc=self.keep_icc.isChecked(), output_path=self.output_path.text().strip(),
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
        path = QFileDialog.getExistingDirectory(self, self.t("选择导出路径"), self.output_path.text())
        if path:
            self.output_path.setText(path)

    def update_estimate(self) -> None:
        selected = self._selected_path()
        if self.source is None or selected is None or self.source_path != selected:
            return
        key = self._estimate_key(selected)
        if key in self._estimate_cache or key in self._estimate_active_keys:
            return
        self._start_estimate((key, selected, self.source))

    def _start_estimate(self, task: tuple[tuple, Path, object]) -> None:
        if self.estimate_worker is not None and self.estimate_worker.isRunning():
            self.estimate_worker.cancel()
            self._estimate_pending = True
            return
        worker = EstimateWorker([task], deepcopy(self.layers), replace(self.settings))
        self.estimate_worker = worker
        self._estimate_active_keys = {task[0]}
        worker.estimated.connect(self._store_estimate)
        worker.failed.connect(lambda key: self._store_estimate(key, None))
        worker.finished.connect(lambda current=worker: self._estimate_finished(current))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _estimate_key(self, path: Path) -> tuple:
        try:
            resolved = path.resolve()
            stat = resolved.stat()
            source = str(resolved), stat.st_mtime_ns, stat.st_size
        except OSError:
            source = str(path), 0, 0
        settings = self.settings
        export = settings.format, settings.quality, settings.resize_mode, settings.resize_value, settings.allow_upscale, settings.keep_exif, settings.keep_icc
        return source, export, tuple(repr(layer) for layer in self.layers)

    def _selected_path(self) -> Path | None:
        item = self.thumbnails.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _store_estimate(self, key: tuple, estimated: float | None) -> None:
        self._estimate_cache[key] = estimated
        self._refresh_estimate_labels()

    def _refresh_estimate_labels(self) -> None:
        selected = self._selected_path()
        current = self._estimate_cache.get(self._estimate_key(selected)) if selected is not None else None
        self.current_estimate.setText(self.t("当前照片约 {size}").format(size=self._bytes(current)) if current is not None else self.t("当前照片约 —"))

    def _estimate_finished(self, worker: EstimateWorker) -> None:
        if self.estimate_worker is not worker:
            return
        self.estimate_worker = None
        self._estimate_active_keys.clear()
        self._refresh_estimate_labels()
        if self._estimate_pending:
            self._estimate_pending = False
            self.update_estimate()

    @staticmethod
    def _bytes(value: float) -> str:
        return f"{value / 1024 / 1024:.1f} MB"

    def save_preset(self) -> None:
        name_dialog = QInputDialog(self)
        name_dialog.setWindowTitle(self.t("保存预设"))
        name_dialog.setLabelText(f"{self.t('预设名称')}:")
        name_dialog.setInputMode(QInputDialog.InputMode.TextInput)
        name_dialog.setMinimumWidth(260)
        accepted = name_dialog.exec() == QDialog.DialogCode.Accepted
        name = name_dialog.textValue()
        if accepted and name.strip():
            name = name.strip()
            try:
                exists = preset_exists(name)
            except ValueError:
                QMessageBox.warning(self, self.t("无法保存预设"), self.t("预设名称无效"))
                return
            if exists:
                dialog = QMessageBox(self)
                dialog.setWindowTitle(self.t("覆盖预设"))
                dialog.setText(self.t("已存在同名预设，是否覆盖？"))
                overwrite = dialog.addButton(self.t("覆盖"), QMessageBox.ButtonRole.AcceptRole)
                dialog.addButton(self.t("取消"), QMessageBox.ButtonRole.RejectRole)
                dialog.exec()
                if dialog.clickedButton() is not overwrite:
                    return
            try:
                save_preset(name, self.layers, self.settings)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, self.t("无法保存预设"), str(exc))
                return
            self.refresh_presets()
            self.preset.setCurrentText(name)

    def open_preset_directory(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(preset_directory())))

    def refresh_presets(self) -> None:
        self.preset.blockSignals(True)
        self.preset.clear(); self.preset.addItem(self.t("预设")); self.preset.addItems(load_presets())
        self.preset.blockSignals(False)

    def apply_preset(self, name: str) -> None:
        preset = load_presets().get(name)
        if preset is None:
            return
        preset_layers, settings = preset
        self.settings = settings
        self.layers = []
        self.layer_list.clear()
        for layer in preset_layers:
            self.add_layer(layer)
        self.format.setCurrentText(settings.format)
        self.quality.setValue(settings.quality)
        self.resize_mode.setCurrentIndex(list(ResizeMode).index(settings.resize_mode))
        self.resize_value.setText(str(round(settings.resize_value)) if settings.resize_value else "")
        self.allow_upscale.setChecked(not settings.allow_upscale)
        self.keep_exif.setChecked(settings.keep_exif)
        self.keep_icc.setChecked(settings.keep_icc)
        self.output_path.setText(settings.output_path)

    def export_batch(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.paths:
            QMessageBox.information(self, self.t("没有图片"), self.t("请先打开或拖入图片。"))
            return
        destination = self.settings.output_path or QFileDialog.getExistingDirectory(self, self.t("选择导出路径"))
        if not destination:
            return
        self.worker = ExportWorker(list(self.paths), Path(destination), deepcopy(self.layers), replace(self.settings))
        self.worker.progressed.connect(lambda current, total, name: self.status.showMessage(self.t("导出 {current}/{total}: {name}").format(current=current, total=total, name=name)))
        self.worker.finished_batch.connect(self.export_finished)
        self.worker.finished.connect(lambda current=self.worker: self._export_worker_finished(current))
        self.worker.finished.connect(self.worker.deleteLater)
        self.export_button.setEnabled(False)
        self.worker.start()

    def _export_worker_finished(self, worker: ExportWorker) -> None:
        if self.worker is worker:
            self.worker = None
            self.export_button.setEnabled(True)

    def export_finished(self, complete: int, failures: list[str]) -> None:
        message = self.t("已导出 {count} 张图片。").format(count=complete)
        if failures:
            message += "\n" + self.t("失败 {count} 张：").format(count=len(failures)) + "\n" + "\n".join(failures[:3])
        QMessageBox.information(self, self.t("导出完成"), message)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About MeiWatermark",
            "MeiWatermark\nVersion 1.096\nGPL-3.0-or-later\n\n©2026 MeiStingray, Kicity Studio\nwww.kicity.com",
        )
