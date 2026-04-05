from __future__ import annotations

from pathlib import Path

from aqt.qt import (
    QColor,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QRect,
    Qt,
)

_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.png"


def _create_fallback_brand_pixmap(theme_mode: str = "dark", size: int = 64) -> QPixmap:
    background = QColor("#182430" if theme_mode == "dark" else "#ffffff")
    border = QColor("#9d86ff")
    accent = QColor("#11d7d6")

    pixmap = QPixmap(size, size)
    pixmap.fill(background)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(QPen(border, max(2, size // 20)))
    painter.drawRect(3, 3, size - 6, size - 6)

    painter.setPen(QPen(accent, max(2, size // 20)))
    painter.drawLine(size // 4, size - 15, size // 4, size // 4)
    painter.drawLine(size // 4, size // 4, size // 2, size // 2)
    painter.drawLine(size // 2, size // 2, size - 14, size // 4 + 2)
    painter.end()
    return pixmap


def create_brand_pixmap(size: int = 64, theme_mode: str = "dark") -> QPixmap:
    if _LOGO_PATH.is_file():
        pixmap = QPixmap(str(_LOGO_PATH))
        if not pixmap.isNull():
            return pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    return _create_fallback_brand_pixmap(theme_mode=theme_mode, size=size)


def _create_square_brand_pixmap(size: int = 64, theme_mode: str = "dark") -> QPixmap:
    if _LOGO_PATH.is_file():
        pixmap = QPixmap(str(_LOGO_PATH))
        if not pixmap.isNull():
            side = min(pixmap.width(), pixmap.height())
            x_offset = max(0, (pixmap.width() - side) // 2)
            y_offset = max(0, (pixmap.height() - side) // 2)
            cropped = pixmap.copy(QRect(x_offset, y_offset, side, side))
            return cropped.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    return _create_fallback_brand_pixmap(theme_mode=theme_mode, size=size)


def create_brand_icon(theme_mode: str = "dark") -> QIcon:
    icon = QIcon()
    for size in (32, 48, 64, 96, 128, 256):
        icon.addPixmap(_create_square_brand_pixmap(size=size, theme_mode=theme_mode))
    return icon
