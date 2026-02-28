import json
import os
import re
import time
import logging
from typing import Optional
from app.services.ai.promt import prompt, QUIZ_SCHEMA
from google.genai import Client

logger = logging.getLogger(__name__)


class AIQuizParser:

    def __init__(self, api_key: Optional[str] = None):
        self.client = Client(
            api_key="AIzaSyBKBVgVGSS1nAwCSq-aPi9mlgmpI4kir54"
        )
        self.prompt = prompt
        self.quiz_schema=QUIZ_SCHEMA

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
                config={
                    "response_mime_type": "application/json",
                    "response_schema": self.quiz_schema,
                }
            )

            logger.info("✅ Model javobi olindi")

            try:
                result = json.loads(response.text)
                print("✅ JSON muvaffaqiyatli ajratildi")
            except Exception as e:
                raise ValueError(f"JSON parsing error: {e}\nRaw response: {response.text}")
            return result

        except Exception as e:
            logger.exception(f"❌ PDF parse error with {e}",)


        finally:
            if uploaded_file:
                try:
                    self.client.files.delete(name=uploaded_file.name)
                    logger.info("🧹 Temporary file deleted")
                except Exception:
                    logger.warning("⚠️ Temp file delete failed")
