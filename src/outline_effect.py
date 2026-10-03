from PyQt6.QtWidgets import QGraphicsEffect
from PyQt6.QtGui import QColor, QPainter, QImage, QPixmap
from PyQt6.QtCore import Qt

# 8방향만 찍는다. 원판 전체를 픽셀마다 drawPixmap 하면 자막이 바뀔 때마다 CPU가 급증한다.
_COMPASS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def outline_stamp_offsets(thickness: int, shadow_blur: int):
    """외곽선·그림자 스탬프 좌표. 각 고리당 8방향만 사용한다."""
    t = max(1, int(thickness))
    sharp = []
    for radius in range(1, min(2, t) + 1):
        for dx, dy in _COMPASS:
            sharp.append((dx * radius, dy * radius))

    blur = max(0, int(shadow_blur))
    outer = max(blur, t + 2)
    shadow = []
    for radius in (2, outer):
        for dx, dy in _COMPASS:
            # 아래(+y)로 한 픽셀 치우쳐 입체감을 남긴다.
            shadow.append((dx * radius, dy * radius + 1))
    return list(dict.fromkeys(sharp)), list(dict.fromkeys(shadow))

class ThickOutlineEffect(QGraphicsEffect):
    """
    RichText 및 다국어 폰트를 완벽 지원하는 하이브리드 소프트 섀도우 & 외곽선(스트로크) 이펙트.
    1px 또렷한 솔리드 테두리 + 그 뒤편의 미세 소프트 블러 드롭 섀도우(Hybrid Soft Shadow)를
    동시에 결합하여 글자가 뚱뚱하게 뭉치지 않으면서도 밝은 배경 위에서 극상의 시인성과
    세련된 영화/넷플릭스 스타일 가독성을 제공합니다.
    """
    def __init__(self, thickness: int = 1, color: QColor = None, shadow_blur: int = 4, parent=None):
        super().__init__(parent)
        self.thickness = max(1, int(thickness))
        self.shadow_blur = max(0, int(shadow_blur))
        self.color = color if color is not None else QColor(0, 0, 0, 240)
        self.shadow_color = QColor(0, 0, 0, 38)
        self._precompute_offsets()

    def set_thickness(self, t: int):
        t = max(1, int(t))
        if self.thickness != t:
            self.thickness = t
            self._precompute_offsets()
            self.update()

    def set_shadow_blur(self, b: int):
        b = max(0, int(b))
        if self.shadow_blur != b:
            self.shadow_blur = b
            self._precompute_offsets()
            self.update()

    def set_color(self, c: QColor):
        self.color = c
        self.update()

    def _precompute_offsets(self):
        self._sharp_offsets, self._shadow_offsets = outline_stamp_offsets(self.thickness, self.shadow_blur)

    def boundingRectFor(self, rect):
        m = max(self.thickness, self.shadow_blur) + 6
        return rect.adjusted(-m, -m, m, m)

    def draw(self, painter):
        pixmap, offset = self.sourcePixmap(Qt.CoordinateSystem.LogicalCoordinates)
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            return
        
        img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

        # 1. 미세 소프트 드롭 섀도우 렌더링 (자연스러운 영화/넷플릭스 음영)
        if self._shadow_offsets:
            shadow_mask = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
            shadow_mask.fill(Qt.GlobalColor.transparent)
            mp1 = QPainter(shadow_mask)
            mp1.drawImage(0, 0, img)
            mp1.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            mp1.fillRect(shadow_mask.rect(), self.shadow_color)
            mp1.end()
            shadow_pix = QPixmap.fromImage(shadow_mask)

            for dx, dy in self._shadow_offsets:
                painter.drawPixmap(offset.x() + dx, offset.y() + dy, shadow_pix)

        # 2. 1px 또렷한 솔리드 외곽선 렌더링 (글자 형태를 칼같이 살려줌)
        stroke_mask = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
        stroke_mask.fill(Qt.GlobalColor.transparent)
        mp2 = QPainter(stroke_mask)
        mp2.drawImage(0, 0, img)
        mp2.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        mp2.fillRect(stroke_mask.rect(), self.color)
        mp2.end()
        stroke_pix = QPixmap.fromImage(stroke_mask)

        for dx, dy in self._sharp_offsets:
            painter.drawPixmap(offset.x() + dx, offset.y() + dy, stroke_pix)

        # 3. 원본 텍스트(다양한 폰트 색상 및 화자 하이라이트) 최상단 렌더링
        painter.drawPixmap(offset, pixmap)
