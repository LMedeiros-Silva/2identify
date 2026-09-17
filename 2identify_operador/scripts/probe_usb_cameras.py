"""Briefly probe local OpenCV USB indices without running inference."""

from __future__ import annotations

import argparse
from time import monotonic

import cv2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-index", type=int, default=5)
    parser.add_argument("--frames", type=int, default=3)
    args = parser.parse_args()
    if args.max_index < 0 or not 1 <= args.frames <= 5:
        parser.error("use --max-index >= 0 e --frames entre 1 e 5")
    if hasattr(cv2, "setLogLevel"):
        cv2.setLogLevel(0)

    for index in range(args.max_index + 1):
        capture = cv2.VideoCapture()
        for property_name in ("CAP_PROP_OPEN_TIMEOUT_MSEC", "CAP_PROP_READ_TIMEOUT_MSEC"):
            property_id = getattr(cv2, property_name, None)
            if property_id is not None:
                capture.set(property_id, 2_000)
        started = monotonic()
        frame_times: list[float] = []
        resolution: tuple[int, int] | None = None
        try:
            if capture.open(index, cv2.CAP_ANY):
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                for _ in range(args.frames):
                    valid, frame = capture.read()
                    if valid and frame is not None and frame.ndim == 3:
                        frame_times.append(monotonic())
                        resolution = int(frame.shape[1]), int(frame.shape[0])
        except Exception as error:
            print(f"USB index {index}: ERRO {type(error).__name__}")
        finally:
            capture.release()

        if resolution is None:
            print(f"USB index {index}: indisponível; liberada")
            continue
        fps = (
            (len(frame_times) - 1) / (frame_times[-1] - frame_times[0])
            if len(frame_times) > 1 and frame_times[-1] > frame_times[0]
            else 0.0
        )
        print(
            f"USB index {index}: OK; {resolution[0]}x{resolution[1]}; "
            f"frames={len(frame_times)}; fps≈{fps:.1f}; "
            f"abertura+leitura={monotonic() - started:.2f}s; liberada"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
