import hashlib
import logging
import os
from typing import Dict
from io import BytesIO
import re
import PIL
import fitz
import numpy as np
from PIL import Image


class PDFService:
    def __init__(self, image_dir: str = "media/quiz/images"):
        self.image_dir = image_dir
        os.makedirs(self.image_dir, exist_ok=True)

    @staticmethod
    def is_blank_image(im: Image.Image, threshold: float = 5.0) -> bool:

        gray = im.convert("L")
        arr = np.array(gray)

        variance = arr.var()

        return variance < threshold

    async def extract_images(self,
                       pdf_file: str,
                       min_width: int = 20,
                       min_height: int = 20,
                       page_coverage_threshold: float = 0.5
                       ) -> Dict[str, str]:
        try:
            min_width = int(min_width)
            min_height = int(min_height)
        except ValueError:
            raise ValueError("min_width va min_height butun son bo'lishi kerak")

        images_dict: Dict[str, str] = {}
        seen_xrefs: set[int] = set()

        file_name = os.path.splitext(os.path.basename(pdf_file))[0]
        pdf_img_dir = os.path.join(self.image_dir, file_name)
        os.makedirs(pdf_img_dir, exist_ok=True)

        counter = 1

        with fitz.open(pdf_file) as pdf:
            for page_index, page in enumerate(pdf, start=1):
                page_rect = page.rect   # size of the page
                page_area = page_rect.width * page_rect.height

                for img in page.get_images(full=True):
                    xref = img[0]
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)

                    try:
                        base_image = pdf.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]

                        with PIL.Image.open(BytesIO(image_bytes)) as im:
                            width, height = im.size

                            if width < min_width or height < min_height:
                                continue

                            image_area = width * height
                            if image_area >= page_area * page_coverage_threshold:
                                logging.info(
                                    "⚠️ Rasm  bu sahifaning deyarli butun maydonini egallaydi, o'tkazib yuborilmoqda.")
                                continue

                            if self.is_blank_image(im):
                                logging.info("⚠️ Rasm bo'sh yoki deyarli bo'sh, o'tkazib yuborilmoqda.")
                                continue

                            image_filename = os.path.join(
                                pdf_img_dir,
                                f"image_{counter}.{image_ext}",
                            )
                            im.save(image_filename)
                            images_dict[f"image_{counter}"] = image_filename
                            counter += 1

                    except Exception as e:
                        print(f"⚠️ Rasm ajratishda xatolik: {e}")
                        continue

        return images_dict

    @staticmethod
    def is_test_pdf(pdf_path: str) -> bool:

        patterns = [
            r'\bA[\)\.]', r'\bB[\)\.]', r'\bC[\)\.]', r'\bD[\)\.]',
            r'\(A\)', r'\(B\)', r'\(C\)', r'\(D\)',
        ]
        compiled = [re.compile(p) for p in patterns]

        text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text() + "\n"

        found = {letter: False for letter in 'ABCD'}
        for pattern in compiled:
            if pattern.search(text):
                if 'A' in pattern.pattern:
                    found['A'] = True
                elif 'B' in pattern.pattern:
                    found['B'] = True
                elif 'C' in pattern.pattern:
                    found['C'] = True
                elif 'D' in pattern.pattern:
                    found['D'] = True

        return all(found.values())

    @staticmethod
    def calculate_file_hash(file) -> str:
        sha256 = hashlib.sha256()

        while chunk := file.read(1024 * 1024):  # 1MB chunk
            sha256.update(chunk)

        file.seek(0)
        return sha256.hexdigest()
