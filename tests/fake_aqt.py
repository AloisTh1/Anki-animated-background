from __future__ import annotations

import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRect, QSize, QSizeF, Qt, QUrl
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QMovie, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


def install_fake_aqt() -> None:
    if "aqt" in sys.modules and getattr(sys.modules["aqt"], "_is_fake_aqt", False):
        return

    aqt_module = types.ModuleType("aqt")
    aqt_module._is_fake_aqt = True
    aqt_module.qconnect = lambda signal, slot: signal.connect(slot)

    qt_module = types.ModuleType("aqt.qt")
    qt_module.QApplication = QApplication
    qt_module.QAction = QAction
    qt_module.QCheckBox = QCheckBox
    qt_module.QColor = QColor
    qt_module.QComboBox = QComboBox
    qt_module.QDesktopServices = QDesktopServices
    qt_module.QDialog = QDialog
    qt_module.QDialogButtonBox = QDialogButtonBox
    qt_module.QFileDialog = QFileDialog
    qt_module.QFont = QFont
    qt_module.QFormLayout = QFormLayout
    qt_module.QFrame = QFrame
    qt_module.QGraphicsBlurEffect = QGraphicsBlurEffect
    qt_module.QGraphicsPixmapItem = QGraphicsPixmapItem
    qt_module.QGraphicsScene = QGraphicsScene
    qt_module.QGraphicsView = QGraphicsView
    qt_module.QGroupBox = QGroupBox
    qt_module.QHBoxLayout = QHBoxLayout
    qt_module.QIcon = QIcon
    qt_module.QLabel = QLabel
    qt_module.QLineEdit = QLineEdit
    qt_module.QMenu = QMenu
    qt_module.QMessageBox = QMessageBox
    qt_module.QMovie = QMovie
    qt_module.QPainter = QPainter
    qt_module.QPen = QPen
    qt_module.QPointF = QPointF
    qt_module.QPixmap = QPixmap
    qt_module.QPushButton = QPushButton
    qt_module.QRect = QRect
    qt_module.QSize = QSize
    qt_module.QSizeF = QSizeF
    qt_module.QSizePolicy = QSizePolicy
    qt_module.QSlider = QSlider
    qt_module.QStackedWidget = QStackedWidget
    qt_module.Qt = Qt
    qt_module.QUrl = QUrl
    qt_module.QVBoxLayout = QVBoxLayout
    qt_module.QWidget = QWidget

    utils_module = types.ModuleType("aqt.utils")
    utils_module.askUser = lambda *args, **kwargs: True
    utils_module.showInfo = lambda *args, **kwargs: None
    utils_module.showWarning = lambda *args, **kwargs: None
    utils_module.showCritical = lambda *args, **kwargs: None

    sys.modules["aqt"] = aqt_module
    sys.modules["aqt.qt"] = qt_module
    sys.modules["aqt.utils"] = utils_module
