"""OpenCV face check for the login page.

Uses YuNet to find a face and SFace to compare it with the photos listed in
Grad_role.csv. Youssef Hany is skipped. Run this with the 64-bit project
venv, which has OpenCV; the dashboard process starts it.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

HOST = "127.0.0.1"
PORT = 8003
MATCH_THRESHOLD = 0.363
ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "Grad_role.csv"
MODELS = Path(r"D:\AVEVA\backend2\SCADAPROJECT\models")
YUNET = MODELS / "face_detection_yunet_2023mar.onnx"
SFACE = MODELS / "face_recognition_sface_2021dec.onnx"
SKIP_NAMES = {"youssef hany"}
CAMERA_INDEX = 0


def _cosine_metric() -> int:
    if hasattr(cv2, "FaceRecognizerSF_FR_COSINE"):
        return int(cv2.FaceRecognizerSF_FR_COSINE)
    return int(cv2.FaceRecognizerSF.FR_COSINE)


def read_bgr(path: Path) -> np.ndarray | None:
    try:
        from PIL import Image, ImageOps

        image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        array = np.asarray(image)
        return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    except Exception:
        frame = cv2.imread(str(path))
        if frame is None:
            return None
        return frame


def fit_frame(frame: np.ndarray, longest: int = 800) -> np.ndarray:
    height, width = frame.shape[:2]
    scale = longest / max(height, width)
    if scale >= 1:
        return frame
    return cv2.resize(frame, (int(width * scale), int(height * scale)))


class OpenCVFaces:
    def __init__(self) -> None:
        self.detector = None
        self.detector_size = (0, 0)
        self.recognizer = cv2.FaceRecognizerSF.create(str(SFACE), "")
        self.metric = _cosine_metric()
        self.gallery: list[dict] = []
        self._infer_lock = threading.Lock()

    def detect_largest(self, frame: np.ndarray):
        height, width = frame.shape[:2]
        size = (width, height)
        if self.detector is None:
            self.detector = cv2.FaceDetectorYN.create(str(YUNET), "", size, 0.6, 0.3, 5000)
            self.detector_size = size
        elif self.detector_size != size:
            self.detector.setInputSize(size)
            self.detector_size = size
        result = self.detector.detect(frame)
        faces = result[1] if isinstance(result, tuple) else result
        if faces is None or len(faces) == 0:
            return None
        return max((faces[index] for index in range(faces.shape[0])), key=lambda row: float(row[2]) * float(row[3]))

    def embed(self, frame: np.ndarray, face) -> np.ndarray:
        aligned = self.recognizer.alignCrop(frame, face)
        feature = np.asarray(self.recognizer.feature(aligned), dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(feature))
        if norm == 0:
            return feature
        return feature / norm

    def enroll(self) -> None:
        with CSV_PATH.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                name = (row.get("Names") or "").strip()
                role = (row.get("Role") or "").strip()
                raw_path = (row.get("Image link") or "").strip().strip('"')
                if not name or name.casefold() in SKIP_NAMES or not raw_path:
                    print(f"Face enroll skipped: {name or 'blank row'}")
                    continue
                path = Path(raw_path)
                frame = read_bgr(path) if path.is_file() else None
                if frame is None:
                    print(f"Face enroll skipped, photo missing: {name} ({raw_path})")
                    continue
                frame = fit_frame(frame)
                face = self.detect_largest(frame)
                if face is None:
                    print(f"Face enroll skipped, no face in photo: {name}")
                    continue
                self.gallery.append(
                    {
                        "name": name,
                        "role": role,
                        "feature": self.embed(frame, face),
                    }
                )
                print(f"Face enrolled: {name} ({role})")

    def identify(self, frame: np.ndarray) -> dict:
        with self._infer_lock:
            return self._identify(frame)

    def _identify(self, frame: np.ndarray) -> dict:
        frame = fit_frame(frame)
        face = self.detect_largest(frame)
        if face is None or not self.gallery:
            return {"granted": False, "name": None, "role": None, "score": None, "message": "Access denied"}
        feature = self.embed(frame, face)
        best = None
        best_score = -1.0
        query = feature.reshape(1, -1)
        for person in self.gallery:
            score = float(self.recognizer.match(query, person["feature"].reshape(1, -1), self.metric))
            if score > best_score:
                best = person
                best_score = score
        if best is None or best_score < MATCH_THRESHOLD:
            return {
                "granted": False,
                "name": None,
                "role": None,
                "score": round(best_score, 3),
                "message": "Access denied",
            }
        return {
            "granted": True,
            "name": best["name"],
            "role": best["role"],
            "score": round(best_score, 3),
            "message": "Access granted",
        }


FACES = OpenCVFaces()


class LoginCamera:
    """Keeps camera 0 open in this process and publishes the latest frame."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jpeg = b""
        self._status = {
            "granted": False,
            "name": None,
            "role": None,
            "score": None,
            "message": "Access denied",
            "camera_ok": False,
        }

    def start(self) -> None:
        threading.Thread(target=self._run, name="opencv-camera", daemon=True).start()

    def jpeg(self) -> bytes:
        with self._lock:
            return self._jpeg

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def _run(self) -> None:
        camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        if not camera.isOpened():
            print(f"OpenCV camera {CAMERA_INDEX} did not open")
            return
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        print(f"OpenCV camera {CAMERA_INDEX} opened")
        checks = 0
        while True:
            ok, frame = camera.read()
            if not ok or frame is None or int(frame.max()) == 0:
                time.sleep(0.05)
                continue
            encoded_ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if not encoded_ok:
                continue
            checks += 1
            result = FACES.identify(frame) if checks % 4 == 0 else None
            with self._lock:
                self._jpeg = encoded.tobytes()
                if result is not None:
                    result["camera_ok"] = True
                    self._status = result
                else:
                    self._status["camera_ok"] = True


CAMERA = LoginCamera()


class FaceHandler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/frame.jpg":
            jpeg = CAMERA.jpeg()
            if not jpeg:
                body = b'{"camera_ok": false}'
                self.send_response(HTTPStatus.NOT_FOUND)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self._cors()
            self.end_headers()
            self.wfile.write(jpeg)
            return
        if path == "/status":
            self._send(CAMERA.status())
            return
        if path != "/health":
            self._send({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        self._send(
            {
                "ok": True,
                "camera_ok": CAMERA.status().get("camera_ok", False),
                "enrolled": [{"name": person["name"], "role": person["role"]} for person in FACES.gallery],
            }
        )

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        if path != "/check":
            self._send({"granted": False, "message": "Access denied"}, HTTPStatus.NOT_FOUND)
            return
        array = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(array, cv2.IMREAD_COLOR) if raw else None
        if frame is None:
            self._send({"granted": False, "name": None, "role": None, "score": None, "message": "Access denied"})
            return
        self._send(FACES.identify(frame))

    def _send(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    if not YUNET.is_file() or not SFACE.is_file():
        raise SystemExit(f"OpenCV face models missing in {MODELS}")
    FACES.enroll()
    if not FACES.gallery:
        print("No faces enrolled. Login camera will stay on Access denied.")
    server = ThreadingHTTPServer((HOST, PORT), FaceHandler)
    print(f"OpenCV face recognition: http://{HOST}:{PORT}/health")
    server.serve_forever()


if __name__ == "__main__":
    main()
