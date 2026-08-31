import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    google_api_key: str
    gemini_model: str
    monday_api_token: str
    monday_board_deals: int
    monday_board_work_orders: int
    cors_origins: list[str]


def load_settings() -> Settings:
    def _required(name: str) -> str:
        v = os.getenv(name)
        if not v or not v.strip():
            raise RuntimeError(f"Missing required env var: {name}")
        # strip() defends against pasted trailing newlines / spaces —
        # httpx rejects header values with embedded newlines, which
        # would otherwise 500 every monday.com request on first use.
        return v.strip()

    def _optional(name: str, default: str) -> str:
        return (os.getenv(name) or default).strip()

    return Settings(
        google_api_key=_required("GOOGLE_API_KEY"),
        gemini_model=_optional("GEMINI_MODEL", "gemini-3.6-flash"),
        monday_api_token=_required("MONDAY_API_TOKEN"),
        monday_board_deals=int(_required("MONDAY_BOARD_DEALS")),
        monday_board_work_orders=int(_required("MONDAY_BOARD_WORK_ORDERS")),
        cors_origins=[
            o.strip()
            for o in _optional("CORS_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        ],
    )
