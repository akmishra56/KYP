"""Optional local OCR candidate; explicit configuration is required."""
import io
from .ocr import OCRUnavailable

class RapidOCRExperiment:
    def __init__(self):
        try:
            from rapidocr import RapidOCR
            self.engine=RapidOCR()
        except ImportError as exc:
            raise OCRUnavailable('Install the isolated OCR evaluation requirements first') from exc
    def orient(self,payload):
        from .ocr import TesseractJSOCR
        return TesseractJSOCR().orient(payload)
    def read(self,payload):
        import numpy as np
        from PIL import Image,ImageOps,UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(payload)) as image:
                if image.width*image.height>20000000:raise ValueError('Image exceeds 20 megapixels')
                array=np.asarray(ImageOps.exif_transpose(image).convert('RGB'))[:,:,::-1].copy()
        except (UnidentifiedImageError,OSError) as exc:raise ValueError('Invalid label image') from exc
        result=self.engine(array)
        texts=list(result.txts or [])
        if not texts:raise ValueError('No text detected')
        return {'text':'\n'.join(texts),'ocr_confidence':min(result.scores) if result.scores else None,'confidence_scope':'scan_minimum_line_score','provider':'rapidocr-experiment'}
