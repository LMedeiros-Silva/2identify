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

## Ultralytics YOLOv8 and PPE checkpoint

The PPE detector uses `ultralytics-opencv-headless` 8.4.115, matching the runtime version stored
in the provided custom YOLOv8 checkpoint. The checkpoint metadata declares `AGPL-3.0` and the
local `models/ppe/best.pt` artifact has SHA-256:

`73A87F86E68F7C5091857F48B55BB756A70B88D0217CC35C58EED3969C7EBA20`

- Documentation: https://docs.ultralytics.com/
- License guidance: https://www.ultralytics.com/license

Ultralytics states that proprietary or commercial deployment requires an appropriate commercial
license unless the complete project is distributed under the AGPL-3.0 terms. Licensing must be
resolved before commercial distribution. The checkpoint is intentionally ignored by Git.

