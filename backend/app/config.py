from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SEIEM Filiacion OCR"
    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    operator_username: str = "operador"
    operator_password: str = "cambia-esta-contrasena"
    operator_token: str = "dev-operator-token"
    filiacion_template_path: Path = Path(r"C:\Users\UsuarioGEM\Downloads\Plantilla_filiacion.xlsx")
    export_dir: Path = Path("exports")
    database_url: str = Field(
        default="mysql+pymysql://seiem_app:CAMBIA_ESTA_CONTRASENA@127.0.0.1:3306/seiem_filiacion?charset=utf8mb4"
    )
    upload_dir: Path = Path("uploads")
    max_upload_mb: int = 15
    tesseract_cmd: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    return settings
