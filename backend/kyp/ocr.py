"""Swappable, explicit server-side OCR adapter; never supplies fake output."""
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol
from PIL import Image, ImageOps, UnidentifiedImageError

class OCRUnavailable(RuntimeError):
    pass

class OCRProvider(Protocol):
    def read(self, image: bytes) -> dict: ...

class TesseractOCR:
    def orient(self, image: bytes) -> dict:
        return TesseractJSOCR().orient(image)

    def read(self, image: bytes) -> dict:
        configured = os.getenv('KYP_TESSERACT', 'tesseract')
        executable = shutil.which(configured)
        if not executable:
            raise OCRUnavailable('Tesseract is not installed. Configure KYP_TESSERACT or use reviewed text input.')
        try:
            with Image.open(io.BytesIO(image)) as original:
                if original.width * original.height > 20000000:
                    raise ValueError('Image exceeds 20 megapixels')
                prepared = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.exif_transpose(original)))
                prepared.thumbnail((3000, 3000))
                with tempfile.TemporaryDirectory(prefix='kyp-ocr-') as folder:
                    path = Path(folder) / 'label.png'
                    prepared.save(path)
                    process = subprocess.run([executable, str(path), 'stdout', '-l', 'eng', '--psm', '6', 'tsv'], capture_output=True, timeout=30)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError('Upload a valid supported label image') from exc
        except subprocess.TimeoutExpired as exc:
            raise OCRUnavailable('OCR timed out. Try a smaller, clearer label image.') from exc
        if process.returncode:
            raise OCRUnavailable('OCR engine failed; verify its English language data installation.')
        import csv
        rows = csv.DictReader(io.StringIO(process.stdout.decode('utf-8', errors='replace')), delimiter='\t')
        lines, confidence = {}, []
        for row in rows:
            word = row.get('text', '').strip()
            value = float(row.get('conf', '-1'))
            if not word or value < 0:
                continue
            key = (row['block_num'], row['par_num'], row['line_num'])
            lines.setdefault(key, []).append(word)
            confidence.append(value / 100)
        text = '\n'.join(' '.join(words) for words in lines.values())
        if not text.strip():
            raise ValueError('No text found. Try better lighting or paste the ingredient text.')
        # Conservative scan-level confidence, not falsely precise token confidence.
        return {'text': text, 'ocr_confidence': min(confidence) if confidence else None, 'confidence_scope': 'scan_minimum', 'provider': 'tesseract'}


class TesseractJSOCR:
    """Local WASM fallback when no system Tesseract executable exists."""
    def orient(self, image: bytes) -> dict:
        import json
        from .orientation import choose_orientation
        runtime = Path(__file__).resolve().parents[1] / 'ocr-runtime'
        node = shutil.which('node')
        if not node or not (runtime / 'models' / 'eng.traineddata').exists() or not (runtime / 'node_modules' / 'tesseract.js').exists():
            raise OCRUnavailable('Auto orientation is unavailable. Use Rotate left or Rotate right.')
        try:
            with Image.open(io.BytesIO(image)) as original:
                if original.width * original.height > 20000000:
                    raise ValueError('Image exceeds 20 megapixels')
                prepared = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.exif_transpose(original)))
                prepared.thumbnail((1600, 1600))
                with tempfile.TemporaryDirectory(prefix='kyp-orient-') as folder:
                    paths = []
                    for angle in (0, 90, 180, 270):
                        path = Path(folder) / (str(angle) + '.png')
                        prepared.rotate(-angle, expand=True).save(path)
                        paths.append(str(path))
                    process = subprocess.run([node, str(runtime / 'recognize.mjs'), *paths], cwd=runtime, capture_output=True, timeout=45)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError('Upload a valid supported label image') from exc
        except subprocess.TimeoutExpired as exc:
            raise OCRUnavailable('Auto orientation timed out. Use the rotation controls.') from exc
        if process.returncode:
            raise OCRUnavailable('Auto orientation failed. Use the rotation controls.')
        results = json.loads(process.stdout.decode('utf-8'))
        if not isinstance(results, list) or len(results) != 4:
            raise OCRUnavailable('Unexpected orientation result. Use the rotation controls.')
        return choose_orientation([{'rotation': angle, 'text': item['text']} for angle, item in zip((0, 90, 180, 270), results)])

    def read(self, image: bytes) -> dict:
        runtime = Path(__file__).resolve().parents[1] / 'ocr-runtime'
        node = shutil.which('node')
        if not node or not (runtime / 'models' / 'eng.traineddata').exists() or not (runtime / 'node_modules' / 'tesseract.js').exists():
            raise OCRUnavailable('Run the project-local OCR runtime and English model setup, or configure system Tesseract.')
        try:
            with Image.open(io.BytesIO(image)) as original:
                if original.width * original.height > 20000000:
                    raise ValueError('Image exceeds 20 megapixels')
                prepared = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.exif_transpose(original)))
                prepared.thumbnail((3000, 3000))
                with tempfile.TemporaryDirectory(prefix='kyp-ocr-') as folder:
                    image_path = Path(folder) / 'label.png'
                    prepared.save(image_path)
                    process = subprocess.run([node, str(runtime / 'recognize.mjs'), str(image_path)], cwd=runtime, capture_output=True, timeout=45)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError('Upload a valid supported label image') from exc
        except subprocess.TimeoutExpired as exc:
            raise OCRUnavailable('OCR timed out. Try a smaller label image.') from exc
        if process.returncode:
            raise OCRUnavailable('Local OCR failed. Verify the runtime/model setup.')
        import json
        data = json.loads(process.stdout.decode('utf-8'))
        if not data['text'].strip():
            raise ValueError('No text detected. Try a clearer image.')
        import csv
        rows = list(csv.DictReader(io.StringIO(data.get('tsv', '')), delimiter='\t'))
        words = [{'text': row['text'], 'confidence': float(row['conf']) / 100} for row in rows if row.get('text', '').strip() and float(row.get('conf', '-1')) >= 0]
        return {'text': data['text'], 'ocr_confidence': min((w['confidence'] for w in words), default=None), 'confidence_scope': 'scan_minimum', 'words': words, 'provider': 'tesseract-local-wasm'}


def default_provider():
    selected = os.getenv('KYP_OCR_ENGINE', 'auto')
    if selected == 'rapidocr':
        from .ocr_experiments import RapidOCRExperiment
        return RapidOCRExperiment()
    if selected == 'tesseractjs': return TesseractJSOCR()
    if selected == 'tesseract': return TesseractOCR()
    if selected != 'auto': raise ValueError('KYP_OCR_ENGINE must be auto, tesseract, tesseractjs or rapidocr')
    if shutil.which(os.getenv('KYP_TESSERACT', 'tesseract')):
        return TesseractOCR()
    return TesseractJSOCR()
