# Third-party notices

## OpenCV

The `opencv-python-headless` dependency is distributed under the OpenCV license. OpenCV
4.5.0 and newer are licensed under Apache License 2.0.

- Project: https://opencv.org/
- License information: https://opencv.org/license/

## YuNet face detector

The configured `face_detection_yunet_2023mar.onnx` artifact is obtained from the official
OpenCV Zoo YuNet directory. The directory declares its files under the MIT License.

- Source and license: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet

## SFace face recognizer

The configured `face_recognition_sface_2021dec.onnx` artifact is obtained from the official
OpenCV Zoo SFace directory. The directory declares its files under Apache License 2.0.

- Source and license: https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface

The model files are installation artifacts and are intentionally ignored by Git. Use
`python scripts/download_face_models.py` to download the pinned artifacts and verify their
SHA-256 checksums.

