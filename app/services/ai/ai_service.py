import json
import os
import re
import time
import logging
from typing import Optional
from app.services.ai.promt import prompt
from google.genai import Client

logger = logging.getLogger(__name__)


class AIQuizParser:

    def __init__(self, api_key: Optional[str] = None):
        self.client = Client(
            api_key="AIzaSyANtKj72-J5hNdTyZZ0COD11I0XO-JcIkc"
        )
        self.prompt = prompt

    @staticmethod
    def extract_json(text: str) -> str:
        if not text:
            raise ValueError("Bo'sh javob qaytdi")

        cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()

        match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("JSON topilmadi")
        return match.group(0)

    def wait_until_ready(self, file_name: str, timeout: int = 120):
        """Google fayl PROCESSING holatidan chiqishini kutadi."""
        start = time.time()

        while True:
            file = self.client.files.get(name=file_name)
            state = file.state.name

            logger.info("File state: %s", state)

            if state == "ACTIVE":
                return file

            if state == "FAILED":
                raise RuntimeError("Google serverida fayl processing FAILED")

            if time.time() - start > timeout:
                raise TimeoutError("Fayl processing timeout")

            time.sleep(2)

    def parse_pdf(self, pdf_path: str) -> str:
        """
        Main pipeline:
        upload → wait → generate → extract JSON
        """
        uploaded_file = None

        try:
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"Fayl topilmadi: {pdf_path}")

            logger.info("📄 Uploading PDF: %s", pdf_path)

            with open(pdf_path, "rb") as f:
                uploaded_file = self.client.files.upload(
                    file=f,
                    config={"mime_type": "application/pdf"},
                )

            uploaded_file = self.wait_until_ready(uploaded_file.name)

            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[self.prompt, uploaded_file],
            )

            raw_text = response.text
            logger.info("✅ Model javobi olindi")

            # ---------- extract ----------
            try:
                clean_json = json.loads(raw_text)
                print("Direct JSON parse successful!")
            except json.JSONDecodeError:
                print("Direct JSON parse failed")
                #text file save
                file_name = pdf_path.split("/")[-1].split(".")[0]
                text_file = f'media/quiz/txt/{file_name}.txt'
                logger.info("📂 Saving raw text to: %s", text_file)
                with open(text_file, "w", encoding="utf-8") as f:
                    f.write(raw_text)
                clean_json = self.extract_json(raw_text)
            print("Extracted JSON:", clean_json)
            return clean_json

        except Exception as e:
            logger.exception(f"❌ PDF parse error with {e}",)


        finally:
            if uploaded_file:
                try:
                    self.client.files.delete(name=uploaded_file.name)
                    logger.info("🧹 Temporary file deleted")
                except Exception:
                    logger.warning("⚠️ Temp file delete failed")
