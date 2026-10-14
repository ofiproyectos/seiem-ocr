from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, IsolatedAsyncioTestCase
from unittest.mock import patch, AsyncMock

import prueba
from fastapi import HTTPException
from pytesseract import TesseractNotFoundError
from backend.app.services import ocr_service


class TesseractConfigTests(TestCase):
    def test_cached_executable_is_checked_again_if_removed(self):
        with TemporaryDirectory() as directory:
            executable = Path(directory) / "tesseract.exe"
            executable.touch()
            with patch.dict(prueba._TESSERACT_CONFIGURED, {"cmd": None, "languages_checked": False}), patch.object(prueba.pytesseract.pytesseract, "tesseract_cmd", "tesseract"), patch.object(prueba.pytesseract, "get_languages", return_value=["spa"]) as languages:
                prueba.configurar_tesseract(str(executable))
                prueba.configurar_tesseract(str(executable))
                self.assertEqual(languages.call_count, 1)
                executable.unlink()
                with self.assertRaises(prueba.TesseractConfigurationError):
                    prueba.configurar_tesseract(str(executable))
                self.assertFalse(prueba._TESSERACT_CONFIGURED["languages_checked"])

    def test_failed_start_is_not_cached_and_can_be_retried(self):
        with TemporaryDirectory() as directory:
            executable = Path(directory) / "tesseract.exe"
            executable.touch()
            with patch.dict(prueba._TESSERACT_CONFIGURED, {"cmd": None, "languages_checked": False}), patch.object(prueba.pytesseract.pytesseract, "tesseract_cmd", "tesseract"), patch.object(prueba.pytesseract, "get_languages", side_effect=[TesseractNotFoundError(), ["spa"]]):
                with self.assertRaises(TesseractNotFoundError):
                    prueba.configurar_tesseract(str(executable))
                self.assertFalse(prueba._TESSERACT_CONFIGURED["languages_checked"])
                prueba.configurar_tesseract(str(executable))
                self.assertTrue(prueba._TESSERACT_CONFIGURED["languages_checked"])


class OcrUnavailableTests(IsolatedAsyncioTestCase):
    async def test_missing_engine_is_server_error_and_upload_is_cleaned(self):
        with TemporaryDirectory() as directory:
            upload = Path(directory) / "document.jpg"
            upload.touch()
            with patch.object(ocr_service, "save_upload_temporarily", new=AsyncMock(return_value=upload)), patch.object(ocr_service, "run_in_threadpool", new=AsyncMock(side_effect=TesseractNotFoundError())), patch.object(ocr_service.logger, "exception") as log:
                with self.assertRaises(HTTPException) as error:
                    await ocr_service.extract_document("acta", None)
                self.assertEqual(error.exception.status_code, 503)
                self.assertIn("servidor", error.exception.detail)
                self.assertNotIn("AppData", error.exception.detail)
                self.assertFalse(upload.exists())
                log.assert_called_once()
