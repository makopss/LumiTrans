import sys
import unittest
import numpy as np
from PIL import Image
sys.path.insert(0, ".")

from src.isolated_ocr import get_isolated_ocr, shutdown_isolated_ocr

class TestIsolatedOCR(unittest.TestCase):
    def test_numpy_and_pil_inference(self):
        ocr = get_isolated_ocr()
        
        # 1. NumPy image
        np_img = np.zeros((100, 400, 3), dtype=np.uint8)
        np_img[30:70, 40:360] = 255
        res_np, el_np = ocr(np_img)
        self.assertTrue(el_np is None or isinstance(el_np, (float, list)))
        
        # 2. PIL Image
        pil_img = Image.fromarray(np_img)
        res_pil, el_pil = ocr(pil_img)
        self.assertTrue(el_pil is None or isinstance(el_pil, (float, list)))
        
        # 3. None input safety
        res_none, el_none = ocr(None)
        self.assertIsNone(res_none)

    @classmethod
    def tearDownClass(cls):
        shutdown_isolated_ocr()

if __name__ == "__main__":
    unittest.main()
