"""Safe conversion boundary between OpenCV frames and Qt-owned images."""

from PySide6.QtGui import QImage

from app.vision.types import Frame


def frame_to_qimage(frame: Frame) -> QImage:
    """Convert a BGR OpenCV frame to an owned RGB QImage."""

    rgb_frame = frame[:, :, ::-1].copy()
    height, width, channels = rgb_frame.shape
    bytes_per_line = width * channels
    image = QImage(
        rgb_frame.data,
        width,
        height,
        bytes_per_line,
        QImage.Format.Format_RGB888,
    )
    return image.copy()
