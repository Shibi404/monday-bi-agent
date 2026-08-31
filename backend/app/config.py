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
        if not v:
            raise RuntimeError(f"Missing required env var: {name}")
        return v

    return Settings(
        google_api_key=_required("GOOGLE_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        monday_api_token=_required("MONDAY_API_TOKEN"),
        monday_board_deals=int(_required("MONDAY_BOARD_DEALS")),
        monday_board_work_orders=int(_required("MONDAY_BOARD_WORK_ORDERS")),
        cors_origins=[
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        ],
    )
