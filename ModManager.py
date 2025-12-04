import ast
import sys
import os
import shutil
import xml.etree.ElementTree as ET
import re
import subprocess
import send2trash # I have no idea why I am making this cross-platform. But this will ensure recycle bin support.

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QListWidget, QListWidgetItem, QLabel,
    QLineEdit, QPushButton, QMessageBox, QMenu,
    QAbstractItemView, QSplitter, QFrame, QStyle, 
    QStyledItemDelegate, QStyleOptionButton, QDialog,
    QTextEdit, QStackedWidget, QProgressBar
)
from PyQt6.QtCore import (
    Qt, QMimeData, QUrl, QRect, QPoint, QSize, 
    QRunnable, QThreadPool, pyqtSignal, QObject, QTimer, QEvent
)
from PyQt6.QtGui import (
    QPixmap, QDrag, QDesktopServices, QColor, 
    QFont, QCursor, QPainter, QPen, QImage,
)

MODS_DIR = "Mods"
PACKAGE_DIR = "Package"
LOAD_ORDER_FILE = "loadorder.txt"
DEFAULT_IMAGE_EXTS = ['.jpg', '.png', '.webp', '.jpeg', '.bmp']

IGNORED_PACKAGES = {
    '_Elona', '_Lang_Chinese', 'Mod_FixedPackageLoader', 'Mod_Slot'
}

# --------------------------
# Stylesheet
# --------------------------
STYLESHEET = """
QMainWindow { background-color: #1e1e1e; }
QDialog { background-color: #1e1e1e; }
QLabel { color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QLineEdit {
    background-color: #2d2d2d; border: 1px solid #3e3e3e;
    border-radius: 4px; color: #ffffff; padding: 6px; font-size: 14px;
}
QLineEdit:focus { border: 1px solid #0078d4; }
QListWidget {
    background-color: #252526; border: 1px solid #3e3e3e;
    border-radius: 4px; outline: none;
}
QPushButton {
    background-color: #3e3e3e; color: white; border: none;
    padding: 8px 16px; border-radius: 4px; font-weight: bold;
}
QPushButton:hover { background-color: #4e4e4e; }
QPushButton:pressed { background-color: #0078d4; }
QPushButton:disabled { background-color: #2e2e2e; color: #777; }
QProgressBar {
    border: 1px solid #3e3e3e;
    border-radius: 4px;
    text-align: center;
    background-color: #2d2d2d;
    color: white;
}
QProgressBar::chunk {
    background-color: #0078d4;
    width: 20px;
}
"""

# --------------------------
# Helpers & Caching
# --------------------------

class ImageCache:
    _cache = {}
    
    @classmethod
    def get_icon(cls, path):
        if not path: return None
        return cls._cache.get(path)

    @classmethod
    def store_image(cls, path, qimage):
        if path and qimage and not qimage.isNull():
            pix = QPixmap.fromImage(qimage)
            icon = pix.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            cls._cache[path] = icon

# --------------------------
# Threading Workers
# --------------------------

class WorkerSignals(QObject):
    finished = pyqtSignal(list)

class ModLoaderWorker(QRunnable):
    """Background task to parse XML and load images."""
    def __init__(self, mod_dirs):
        super().__init__()
        self.mod_dirs = mod_dirs
        self.signals = WorkerSignals()

    def run(self):
        loaded_mods = []
        for path in self.mod_dirs:
            mod = ModData(path)
            mod.load_details() 
            loaded_mods.append(mod)
        self.signals.finished.emit(loaded_mods)

# --------------------------
# Data Logic
# --------------------------

class ModData:
    def __init__(self, folder_path):
        self.source_path = os.path.abspath(folder_path)
        self.folder_name = os.path.basename(folder_path)
        self.xml_path = os.path.join(folder_path, "package.xml")
        
        self.title = self.folder_name
        self.id = ""
        self.version = "?"
        self.author = "?"
        self.description = "No description available."
        self.preview_path = None
        self.enabled = False 
        self.valid_xml = False
        self.loaded = False
        self.cached_qimage = None

    def load_details(self):
        self.parse_xml()
        self.find_preview()
        if self.preview_path:
            img = QImage(self.preview_path)
            if not img.isNull():
                self.cached_qimage = img
        self.loaded = True

    def parse_xml(self):
        if not os.path.exists(self.xml_path):
            return
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
            def get_text(tag):
                node = root.find(tag)
                return node.text if node is not None else ""

            self.title = get_text('title') or self.title
            self.id = get_text('id')
            self.version = get_text('version') or "?"
            self.author = get_text('author') or "?"
            desc = get_text('description')
            if desc: self.description = desc
            self.valid_xml = True
        except Exception:
            self.description = "Error parsing XML"

    def find_preview(self):
        try:
            for f in os.listdir(self.source_path):
                ext = os.path.splitext(f)[1].lower()
                if "preview" in f.lower() and ext in DEFAULT_IMAGE_EXTS:
                    self.preview_path = os.path.join(self.source_path, f)
                    break
        except OSError:
            pass

    def get_link_name(self):
        clean = re.sub(r'[<>:"/\\|?*]', '', self.title).strip()
        if not clean:
            clean = f"Unknown_{self.folder_name}"
        return clean

# --------------------------
# Custom Delegate
# --------------------------

class ModListDelegate(QStyledItemDelegate):
    
    PADDING = 6
    ICON_SIZE = 40
    CHECKBOX_SIZE = 20
    INDEX_WIDTH = 30
    
    toggled = pyqtSignal(ModData)

    def __init__(self, parent=None, is_active_list=True):
        super().__init__(parent)
        self.is_active_list = is_active_list

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 56)

    def paint(self, painter, option, index):
        mod_data = index.data(Qt.ItemDataRole.UserRole)
        if not mod_data: return

        painter.save()

        is_dimmed = self.is_active_list and not mod_data.enabled
        is_highlighted_active = self.is_active_list and mod_data.enabled

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#0078d4"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor("#2d2d2d"))

        if is_highlighted_active and not (option.state & QStyle.StateFlag.State_Selected):
            painter.fillRect(option.rect.x(), option.rect.y(), 4, option.rect.height(), QColor("#0099ff"))

        if is_dimmed and not (option.state & QStyle.StateFlag.State_Selected):
            title_color = QColor("#999999")
            sub_color = QColor("#777777")
            icon_opacity = 0.6
        else:
            title_color = QColor("white")
            sub_color = QColor("#dddddd") if option.state & QStyle.StateFlag.State_Selected else QColor("#bbbbbb")
            icon_opacity = 1.0

        if not mod_data.valid_xml:
            if is_dimmed and not (option.state & QStyle.StateFlag.State_Selected):
                title_color = QColor("#a05050")
            else:
                title_color = QColor("#ff5555")
        
        rect = QRect(option.rect)
        rect.setLeft(rect.left() + self.PADDING)
        
        if self.is_active_list:
            painter.setPen(QColor("#888888"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(rect.left(), rect.top(), self.INDEX_WIDTH, rect.height(), 
                           Qt.AlignmentFlag.AlignCenter, str(index.row() + 1))
            rect.setLeft(rect.left() + self.INDEX_WIDTH + self.PADDING)
            
            cb_rect = QRect(rect.left(), rect.top() + (rect.height() - self.CHECKBOX_SIZE) // 2, 
                          self.CHECKBOX_SIZE, self.CHECKBOX_SIZE)
            
            opt = QStyleOptionButton()
            opt.rect = cb_rect
            opt.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Active
            opt.state |= QStyle.StateFlag.State_On if mod_data.enabled else QStyle.StateFlag.State_Off
            
            if is_dimmed: painter.setOpacity(0.8)
            QApplication.style().drawControl(QStyle.ControlElement.CE_CheckBox, opt, painter)
            if is_dimmed: painter.setOpacity(1.0)

            rect.setLeft(rect.left() + self.CHECKBOX_SIZE + self.PADDING * 2)

        icon_rect = QRect(rect.left(), rect.top() + (rect.height() - self.ICON_SIZE) // 2, 
                        self.ICON_SIZE, self.ICON_SIZE)
        
        painter.save()
        painter.setOpacity(icon_opacity)

        pix = ImageCache.get_icon(mod_data.preview_path)
        if pix: painter.drawPixmap(icon_rect, pix)
        else:
            painter.setPen(QColor("#444")); painter.setBrush(QColor("#333")); painter.drawRect(icon_rect)
            painter.setPen(QColor("#555")); painter.setFont(QFont("Segoe UI", 7)); painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "IMG")
            
        painter.restore()

        rect.setLeft(rect.left() + self.ICON_SIZE + self.PADDING * 2)

        text_rect = QRect(rect.left(), rect.top() + 8, rect.width() - self.PADDING, 20)
        painter.setPen(title_color); painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(text_rect, Qt.TextFlag.TextSingleLine, mod_data.title)
        
        text_rect.moveTop(text_rect.bottom() + 2)
        painter.setPen(sub_color); painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(text_rect, Qt.TextFlag.TextSingleLine, f"v{mod_data.version} - {mod_data.author}")

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if self.is_active_list and event.type() == QEvent.Type.MouseButtonRelease:
            mod_data = index.data(Qt.ItemDataRole.UserRole)
            if not mod_data: return False

            left_offset = self.PADDING + self.INDEX_WIDTH + self.PADDING
            cb_rect = QRect(option.rect.left() + left_offset, 
                          option.rect.top() + (option.rect.height() - self.CHECKBOX_SIZE) // 2,
                          self.CHECKBOX_SIZE, self.CHECKBOX_SIZE)
            
            hit_rect = cb_rect.adjusted(-2, -2, 2, 2)
            if hit_rect.contains(event.position().toPoint()):
                mod_data.enabled = not mod_data.enabled
                self.toggled.emit(mod_data)
                return True

        return super().editorEvent(event, model, option, index)

# --------------------------
# Custom Widgets
# --------------------------

class ModDetailsDialog(QDialog):
    """A dialog to show comprehensive details about a single mod."""
    def __init__(self, mod_data, source_list_is_active, parent=None):
        super().__init__(parent)
        self.mod = mod_data
        self.setWindowTitle(f"Details: {self.mod.title}")
        self.setMinimumSize(700, 500)
        self.setStyleSheet(STYLESHEET) 

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Left Side (Image)
        img_container = QFrame()
        img_container.setFixedWidth(320)
        img_layout = QVBoxLayout(img_container)
        img_layout.setContentsMargins(0, 0, 0, 0)
        
        self.img_label = QLabel("No Preview Available")
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background-color: #000; border: 1px solid #333; color: #555;")
        self.img_label.setMinimumHeight(320)
        img_layout.addWidget(self.img_label)
        img_layout.addStretch()
        main_layout.addWidget(img_container)

        # Right Side (Details)
        details_container = QWidget()
        details_layout = QVBoxLayout(details_container)
        details_layout.setContentsMargins(0,0,0,0)
        details_layout.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold; font-size: 18px; color: white;")
        self.title_label.setWordWrap(True)
        details_layout.addWidget(self.title_label)

        self.meta_label = QLabel()
        self.meta_label.setStyleSheet("color: #aaa; font-size: 11px;")
        details_layout.addWidget(self.meta_label)
        
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-weight: bold; font-size: 12px; margin-top: 10px; margin-bottom: 5px;")
        details_layout.addWidget(self.status_label)

        self.desc_area = QTextEdit()
        self.desc_area.setReadOnly(True)
        self.desc_area.setStyleSheet("""
            QTextEdit {
                background-color: #252526;
                border: 1px solid #3e3e3e;
                color: #ddd;
                padding: 5px;
            }
        """)
        details_layout.addWidget(self.desc_area)

        # Bottom Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        details_layout.addLayout(button_layout)
        
        main_layout.addWidget(details_container)
        
        self.populate_data(source_list_is_active)

    def populate_data(self, source_list_is_active):
        if self.mod.preview_path:
            pix = QPixmap(self.mod.preview_path)
            if not pix.isNull():
                scaled = pix.scaled(320, 320, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.img_label.setPixmap(scaled)
                self.img_label.setText("") 
            
        self.title_label.setText(self.mod.title)
        self.meta_label.setText(f"Author: {self.mod.author}  |  Version: {self.mod.version}  |  ID: {self.mod.id}")
        self.desc_area.setText(self.mod.description)

        if source_list_is_active:
            if self.mod.enabled:
                self.status_label.setText("Status: ACTIVE")
                self.status_label.setStyleSheet(self.status_label.styleSheet() + "color: #66bb6a;") # Green
            else:
                self.status_label.setText("Status: INACTIVE (in Load Order)")
                self.status_label.setStyleSheet(self.status_label.styleSheet() + "color: #999;") # Gray
        else:
            self.status_label.setText("Status: UNINSTALLED (in Storage)")
            self.status_label.setStyleSheet(self.status_label.styleSheet() + "color: #ffa726;") # Orange

class ModPreviewPopup(QFrame):
    """Detailed popup with Image and Text."""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("""
            QFrame {
                background-color: #1f1f1f;
                border: 1px solid #444;
                border-radius: 4px;
            }
            QLabel { color: #ccc; }
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background-color: #000; border: 1px solid #333;")
        layout.addWidget(self.img_label)
        
        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: white; margin-top: 5px;")
        self.title_lbl.setWordWrap(True)
        layout.addWidget(self.title_lbl)
        
        self.meta_lbl = QLabel()
        self.meta_lbl.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.meta_lbl)
        
        self.desc_lbl = QLabel()
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setStyleSheet("color: #bbb; font-size: 12px; margin-top: 5px;")
        self.desc_lbl.setMaximumWidth(320)
        layout.addWidget(self.desc_lbl)
        
        self.hide()

    def update_data(self, mod):
        if mod.preview_path:
            pix = QPixmap(mod.preview_path)
            if not pix.isNull():
                scaled = pix.scaled(320, 320, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.img_label.setPixmap(scaled)
                self.img_label.show()
            else:
                self.img_label.hide()
        else:
            self.img_label.hide()
            
        self.title_lbl.setText(mod.title)
        self.meta_lbl.setText(f"ID: {mod.id} | Ver: {mod.version} | Auth: {mod.author}")
        
        desc = mod.description
        if len(desc) > 300: desc = desc[:300] + "..."
        self.desc_lbl.setText(desc)
        
        self.reposition_and_resize()
        self.show()

    def reposition_and_resize(self):
        ideal_size = self.layout().sizeHint()
        self.resize(ideal_size)

        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos).availableGeometry()

        x = cursor_pos.x() + 25
        y = cursor_pos.y() + 25
        
        if x + self.width() > screen.right():
            x = cursor_pos.x() - self.width() - 25
        if y + self.height() > screen.bottom():
            y = screen.bottom() - self.height() - 10
            
        self.move(x, y)

class DraggableListWidget(QListWidget):
    def __init__(self, parent_window, is_active_list):
        super().__init__()
        self.parent_window = parent_window
        self.is_active_list = is_active_list
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setMouseTracking(True)
        
        self.delegate = ModListDelegate(self, is_active_list)
        self.delegate.toggled.connect(self.parent_window.on_mod_toggled)
        self.setItemDelegate(self.delegate)
        
        self.drag_target_row = -1
        self.drag_active = False
        self._drag_pixmap_cache = {} 

    def mouseMoveEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item:
            mod_data = item.data(Qt.ItemDataRole.UserRole)
            self.parent_window.schedule_preview(mod_data)
        else:
            self.parent_window.cancel_preview()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.parent_window.cancel_preview()
        super().leaveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            self.drag_active = True
            event.accept()
            event.setDropAction(Qt.DropAction.MoveAction)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drag_active = False
        self.drag_target_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            pos = event.position().toPoint()
            item = self.itemAt(pos)
            
            if item:
                rect = self.visualItemRect(item)
                self.drag_target_row = self.row(item) + 1 if pos.y() > rect.y() + rect.height() / 2 else self.row(item)
            else:
                self.drag_target_row = self.count()

            self.viewport().update()
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drag_active and self.drag_target_row != -1:
            painter = QPainter(self.viewport())
            pen = QPen(QColor("#00ffff"), 2)
            painter.setPen(pen)
            
            y = 0
            if self.count() == 0: y = 10 
            elif self.drag_target_row >= self.count():
                y = self.visualItemRect(self.item(self.count()-1)).bottom()
            else:
                y = self.visualItemRect(self.item(self.drag_target_row)).top()
                
            painter.drawLine(0, y, self.width(), y)

    def startDrag(self, supportedActions):
        items = self.selectedItems()
        if not items: return
        drag = QDrag(self)
        mime = QMimeData()
        drag_ids = [id(item.data(Qt.ItemDataRole.UserRole)) for item in items]
        mime.setText(str(drag_ids)) 
        
        count = len(items)
        if count not in self._drag_pixmap_cache:
            pix = QPixmap(200, 30)
            pix.fill(QColor(0, 0, 0, 0)) 
            painter = QPainter(pix)
            painter.setBrush(QColor(0, 120, 212, 200)) 
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(0, 0, 200, 30)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(QRect(10, 0, 190, 30), Qt.AlignmentFlag.AlignVCenter, f"Moving {count} mod(s)...")
            painter.end()
            self._drag_pixmap_cache[count] = pix
            
        drag.setPixmap(self._drag_pixmap_cache[count])
        drag.setHotSpot(QPoint(10, 15))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        self.drag_active = False
        self.drag_target_row = -1
        self.viewport().update()

        try:
            source_ids = ast.literal_eval(event.mimeData().text())
        except: return

        items_to_move = []
        source_list = None
        
        for lst in [self.parent_window.list_active, self.parent_window.list_storage]:
            for i in range(lst.count()):
                item = lst.item(i)
                mod = item.data(Qt.ItemDataRole.UserRole)
                if id(mod) in source_ids:
                    items_to_move.append((mod, lst, item))
                    source_list = lst
            if items_to_move: break
            
        if not items_to_move: return

        pos = event.position().toPoint()
        target_item = self.itemAt(pos)
        insert_row = self.count()
        if target_item:
            rect = self.visualItemRect(target_item)
            insert_row = self.row(target_item)
            if pos.y() > rect.y() + rect.height() / 2:
                insert_row += 1

        if source_list == self:
            original_rows = sorted([self.row(x[2]) for x in items_to_move])
            count_removed_above = sum(1 for r in original_rows if r < insert_row)
            insert_row -= count_removed_above

        for _, lst, item in items_to_move:
            lst.takeItem(lst.row(item))
            
        insert_row = max(0, min(insert_row, self.count()))

        for mod, _, _ in items_to_move:
            if source_list != self:
                mod.enabled = self.is_active_list
            
            new_item = QListWidgetItem()
            new_item.setData(Qt.ItemDataRole.UserRole, mod)
            self.insertItem(insert_row, new_item)
            insert_row += 1

        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self.parent_window.update_lists_state()

# --------------------------
# Main Window
# --------------------------

class ModManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Elin Mod Manager")
        self.resize(1200, 800)
        self.existing_links = set()
        self.unsaved_changes = False
        
        self.threadpool = QThreadPool()
        self.preview_timer = QTimer()
        self.preview_timer.setInterval(300) 
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.show_preview_popup)
        self.pending_preview_mod = None
        
        self.preview_popup = ModPreviewPopup()
        
        self.init_ui()
        QTimer.singleShot(100, self.load_data)

    def init_ui(self):
        # Create a Stacked Widget to switch between Loading and Main UI
        self.central_stack = QStackedWidget()
        self.setCentralWidget(self.central_stack)

        # --- Loading Screen (Page 0) ---
        self.loading_widget = QWidget()
        load_layout = QVBoxLayout(self.loading_widget)
        load_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title = QLabel("Elin Mod Manager")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: white; margin-bottom: 20px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.load_status_label = QLabel("Initializing...")
        self.load_status_label.setStyleSheet("color: #aaa; font-size: 14px;")
        self.load_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(400)
        self.progress_bar.setRange(0, 0) # Indeterminate mode
        
        load_layout.addWidget(title)
        load_layout.addWidget(self.progress_bar)
        load_layout.addWidget(self.load_status_label)
        
        self.central_stack.addWidget(self.loading_widget)

        # --- Main App (Page 1) ---
        self.main_app_widget = QWidget()
        layout = QVBoxLayout(self.main_app_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search title, author, or ID...")
        self.search_bar.setFixedWidth(300)
        self.search_bar.textChanged.connect(self.filter_lists)
        
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.load_data)

        self.btn_save = QPushButton("Apply Load Order")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.apply_changes)
        self.btn_save.setFixedWidth(200)

        toolbar.addWidget(self.search_bar)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_save)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        
        left_c = QWidget()
        l_lay = QVBoxLayout(left_c)
        l_lay.setContentsMargins(0, 0, 0, 0)
        lbl_active = QLabel("<b>Load Order (Active)</b>")
        l_lay.addWidget(lbl_active)
        self.list_active = DraggableListWidget(self, True)
        l_lay.addWidget(self.list_active)
        l_lay.addWidget(QLabel("<span style='color: #777; font-size: 11px;'>Drag to reorder. Checkbox to enable.</span>"))
        
        right_c = QWidget()
        r_lay = QVBoxLayout(right_c)
        r_lay.setContentsMargins(0, 0, 0, 0)
        lbl_store = QLabel("<b>Available Storage</b>")
        r_lay.addWidget(lbl_store)
        self.list_storage = DraggableListWidget(self, False)
        r_lay.addWidget(self.list_storage)
        r_lay.addWidget(QLabel("<span style='color: #777; font-size: 11px;'>Drag here to uninstall.</span>"))

        splitter.addWidget(left_c)
        splitter.addWidget(right_c)
        splitter.setStretchFactor(0, 3) 
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.setup_context_menu(self.list_active)
        self.setup_context_menu(self.list_storage)
        
        self.status_frame = QFrame()
        self.status_frame.setFixedHeight(35)
        self.status_frame.setStyleSheet("background-color: #252526; border-top: 1px solid #3e3e3e;")
        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(10, 0, 10, 0)
        self.stat_left = QLabel("Initializing...")
        self.stat_right = QLabel("")
        self.stat_right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_layout.addWidget(self.stat_left)
        status_layout.addStretch()
        status_layout.addWidget(self.stat_right)
        layout.addWidget(self.status_frame)
        
        self.central_stack.addWidget(self.main_app_widget)

    def schedule_preview(self, mod_data):
        if self.pending_preview_mod != mod_data:
            self.pending_preview_mod = mod_data
            self.preview_timer.start()

    def cancel_preview(self):
        self.preview_timer.stop()
        self.pending_preview_mod = None
        self.preview_popup.hide()

    def show_preview_popup(self):
        if self.pending_preview_mod:
            self.preview_popup.update_data(self.pending_preview_mod)

    def closeEvent(self, event):
        if self.unsaved_changes:
            reply = QMessageBox.question(self, 'Unsaved Changes', 
                "You have pending changes.\nQuit without applying?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes: event.accept()
            else: event.ignore()
        else:
            event.accept()

    def on_mod_toggled(self, mod_data):
        self.update_lists_state()

    def update_lists_state(self):
        self.list_active.viewport().update()
        self.list_storage.viewport().update()
        self.calculate_changes()

    def add_mod_to_list(self, list_widget, mod_data):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, mod_data)
        list_widget.addItem(item)

    def load_data(self):
        # Switch to loading screen if explicitly refreshing (optional, but good UX)
        if self.sender() == self.btn_refresh:
             self.load_status_label.setText("Refreshing...")
             self.central_stack.setCurrentIndex(0)

        self.load_status_label.setText("Scanning Mods Folder...")
        self.stat_left.setText("Loading mods (Scanning disk)...")
        self.btn_refresh.setEnabled(False)
        self.list_active.clear()
        self.list_storage.clear()
        
        if not os.path.exists(MODS_DIR): os.makedirs(MODS_DIR)

        dirs = [entry.path for entry in os.scandir(MODS_DIR) if entry.is_dir()] if os.path.exists(MODS_DIR) else []
        
        worker = ModLoaderWorker(dirs)
        worker.signals.finished.connect(self.on_data_loaded)
        self.threadpool.start(worker)

    def on_data_loaded(self, all_mods):
        self.load_status_label.setText("Processing Load Order...")
        self.stat_left.setText("Processing load order...")
        
        for mod in all_mods:
            if mod.cached_qimage:
                ImageCache.store_image(mod.preview_path, mod.cached_qimage)
                mod.cached_qimage = None 

        mods_map = {mod.get_link_name(): mod for mod in all_mods}
        self.existing_links = set() 
        if os.path.exists(PACKAGE_DIR):
            for item in os.listdir(PACKAGE_DIR):
                full_path = os.path.join(PACKAGE_DIR, item)
                if os.path.isdir(full_path) or os.path.islink(full_path):
                    self.existing_links.add(item)

        processed_mods = set() 
        
        self.list_active.setUpdatesEnabled(False)
        self.list_storage.setUpdatesEnabled(False)

        try:
            if os.path.exists(LOAD_ORDER_FILE):
                with open(LOAD_ORDER_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        parts = line.strip().split(',')
                        if not parts[0]: continue
                        link_name = os.path.basename(os.path.normpath(parts[0]))
                        mod = mods_map.get(link_name)
                        
                        if mod and link_name in self.existing_links:
                            mod.enabled = (len(parts) > 1 and parts[1] == '1')
                            self.add_mod_to_list(self.list_active, mod)
                            processed_mods.add(mod)
                            
            for mod in all_mods:
                if mod not in processed_mods:
                    mod.enabled = False 
                    self.add_mod_to_list(self.list_storage, mod)
        finally:
            self.list_active.setUpdatesEnabled(True)
            self.list_storage.setUpdatesEnabled(True)

        self.update_lists_state()
        self.btn_refresh.setEnabled(True)
        self.filter_lists()
        
        # Switch to Main App view
        self.central_stack.setCurrentIndex(1)

    def calculate_changes(self):
        total = self.list_active.count() + self.list_storage.count()
        installed = self.list_active.count()
        
        active_count = 0
        desired = set()
        
        for i in range(self.list_active.count()):
            mod = self.list_active.item(i).data(Qt.ItemDataRole.UserRole)
            if mod.enabled:
                active_count += 1
                desired.add(mod.get_link_name())
        
        self.stat_left.setText(f"Total: {total} | Installed: {installed} | Active: {active_count}")
        
        actual = self.existing_links - IGNORED_PACKAGES
        changes = len(desired.symmetric_difference(actual))
        
        self.unsaved_changes = changes > 0 
        
        if self.unsaved_changes:
            self.stat_right.setText(f"⚠ {changes} link changes pending")
            self.stat_right.setStyleSheet("color: #ffa726; font-weight: bold;")
            self.btn_save.setStyleSheet("background-color: #c62828; color: white;")
        else:
            self.stat_right.setText("✔ Synchronized")
            self.stat_right.setStyleSheet("color: #66bb6a; font-weight: bold;")
            self.btn_save.setStyleSheet("background-color: #3e3e3e;")

    def filter_lists(self):
        txt = self.search_bar.text().lower()
        self.list_active.setUpdatesEnabled(False)
        self.list_storage.setUpdatesEnabled(False)
        try:
            for lst in [self.list_active, self.list_storage]:
                for i in range(lst.count()):
                    item = lst.item(i)
                    mod = item.data(Qt.ItemDataRole.UserRole)
                    match = txt in mod.title.lower() or txt in mod.id.lower() or txt in mod.author.lower()
                    item.setHidden(not match)
        finally:
            self.list_active.setUpdatesEnabled(True)
            self.list_storage.setUpdatesEnabled(True)

    def setup_context_menu(self, list_widget):
        list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        list_widget.customContextMenuRequested.connect(lambda p: self.show_context_menu(p, list_widget))

    def show_context_menu(self, pos, list_widget):
        selected_items = list_widget.selectedItems()
        item_under_cursor = list_widget.itemAt(pos)
        
        if not item_under_cursor:
            return

        mod_under_cursor = item_under_cursor.data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu()
        menu.setStyleSheet(STYLESHEET)
        
        # Single-item actions based on the item under the cursor
        menu.addAction("Show Details", lambda: self.show_mod_details(mod_under_cursor, list_widget.is_active_list))
        menu.addAction("Open Folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(mod_under_cursor.source_path)))
        
        # Batch actions based on the entire selection
        if selected_items:
            count = len(selected_items)
            menu.addSeparator()
            
            # Batch actions for active list
            if list_widget == self.list_active:
                menu.addAction(f"Enable {count} Selected", lambda: self.batch_set(list_widget, True))
                menu.addAction(f"Disable {count} Selected", lambda: self.batch_set(list_widget, False))
                menu.addSeparator()
            
            # Delete action for both lists
            menu.addAction(f"Delete {count} Selected Mod(s)...", lambda: self.delete_selected_mods(list_widget))

        menu.exec(list_widget.mapToGlobal(pos))
        
    def show_mod_details(self, mod, is_active_list):
        dialog = ModDetailsDialog(mod, is_active_list, self)
        dialog.exec()

    def batch_set(self, list_widget, state):
        for item in list_widget.selectedItems():
            mod = item.data(Qt.ItemDataRole.UserRole)
            mod.enabled = state
        self.update_lists_state()

    def apply_changes(self):
        active_mods = [self.list_active.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list_active.count())]

        try:
            if not os.path.exists(PACKAGE_DIR): os.makedirs(PACKAGE_DIR)
            abs_package = os.path.abspath(PACKAGE_DIR)
            
            desired = {mod.get_link_name() for mod in active_mods if mod.enabled}
            self.existing_links = set(os.listdir(abs_package)) 
            
            for item in self.existing_links:
                if item not in IGNORED_PACKAGES and item not in desired:
                    path = os.path.join(abs_package, item)
                    try:
                        if os.path.islink(path): os.unlink(path)
                        elif os.path.isdir(path): shutil.rmtree(path)
                    except: pass 

            lines = []
            for mod in active_mods:
                link_name = mod.get_link_name()
                dest = os.path.join(abs_package, link_name)
                lines.append(f"{dest},{'1' if mod.enabled else '0'}")

                if mod.enabled and not os.path.exists(dest):
                    try:
                        os.symlink(mod.source_path, dest)
                    except OSError:
                        # Let's fall back to junctions on Windows if symlink fails
                        cmd = ['cmd', '/c', 'mklink', '/J', dest, mod.source_path]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            with open(LOAD_ORDER_FILE, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))

            self.load_data()
            QMessageBox.information(self, "Success", "Load order applied.")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def delete_selected_mods(self, list_widget):
        selected_items = list_widget.selectedItems()
        if not selected_items:
            return

        count = len(selected_items)
        plural = "s" if count > 1 else ""
        
        reply = QMessageBox.question(self, 'Confirm Deletion',
            f"Are you sure you want to move {count} mod folder{plural} to the Recycle Bin?\n\n"
            "This permanently removes the mod source files from the Mods folder.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            return

        items_to_remove_from_ui = []
        failed_mods = []

        for item in selected_items:
            mod = item.data(Qt.ItemDataRole.UserRole)
            try:
                send2trash.send2trash(mod.source_path)
                items_to_remove_from_ui.append(item)
            except Exception as e:
                failed_mods.append((mod.title, str(e)))

        # Update the UI by removing items that were successfully deleted
        for item in items_to_remove_from_ui:
            list_widget.takeItem(list_widget.row(item))
        
        self.update_lists_state()  # Recalculate totals and pending changes
        
        # Report the results to the user
        if failed_mods:
            error_details = "\n".join([f"- {title}: {err}" for title, err in failed_mods])
            QMessageBox.warning(self, "Deletion Partially Failed",
                f"Could not delete the following mods:\n\n{error_details}")
        elif items_to_remove_from_ui:
            QMessageBox.information(self, "Success", f"{len(items_to_remove_from_ui)} mod{plural} moved to Recycle Bin.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setFont(QFont("Segoe UI", 10))
    
    window = ModManagerWindow()
    window.show()
    sys.exit(app.exec())