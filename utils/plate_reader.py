"""License plate OCR — EasyOCR with OpenCV preprocessing"""
import cv2, re
import numpy as np
from typing import Optional


class PlateReader:
    PATTERNS = [
        r'^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$',
        r'^\d{2}BH\d{4}[A-Z]{2}$',
    ]

    def __init__(self):
        self.ocr = None
        try:
            import easyocr
            self.ocr = easyocr.Reader(['en'], gpu=False, verbose=False)
        except Exception:
            pass

    def read_from_region(self, frame, bbox, expand=60) -> Optional[str]:
        h,w = frame.shape[:2]
        x1,y1,x2,y2 = bbox
        region = frame[max(0,y2-expand):min(h,y2+expand),
                       max(0,x1-20):min(w,x2+20)]
        return self.extract_plate(region) if region.size else None

    def extract_plate(self, region) -> Optional[str]:
        plate_img = self._find_plate(region) or region
        proc = self._preprocess(plate_img)
        text = self._ocr(proc)
        return self._clean(text) if text else None

    def _find_plate(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.bilateralFilter(gray,11,17,17), 30, 200)
        cnts,_ = cv2.findContours(edges,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cnts,key=cv2.contourArea,reverse=True)[:10]:
            approx = cv2.approxPolyDP(c,0.018*cv2.arcLength(c,True),True)
            if len(approx)==4:
                x,y,w,h = cv2.boundingRect(approx)
                if 2.5 <= w/max(h,1) <= 7.0 and w>60 and h>15:
                    return img[y:y+h,x:x+w]
        return None

    def _preprocess(self, img):
        h,w = img.shape[:2]
        if h<30: img = cv2.resize(img,None,fx=60/max(h,1),fy=60/max(h,1),interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray,h=10)
        return cv2.adaptiveThreshold(denoised,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,11,2)

    def _ocr(self, img) -> Optional[str]:
        if self.ocr:
            try:
                res = self.ocr.readtext(img,detail=1,paragraph=False)
                if res:
                    best = max(res,key=lambda x:x[2])
                    if best[2]>0.3: return best[1]
            except Exception: pass
        try:
            import pytesseract
            return pytesseract.image_to_string(img,
                config='--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789').strip()
        except Exception: return None

    def _clean(self, text) -> Optional[str]:
        c = re.sub(r'[^A-Z0-9]','',text.upper())
        if len(c)<4: return None
        for p in self.PATTERNS:
            if re.match(p,c): return c
        return c if 5<=len(c)<=10 else None
