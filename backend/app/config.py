import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    anthropic_model: str
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
        anthropic_api_key=_required("ANTHROPIC_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        monday_api_token=_required("MONDAY_API_TOKEN"),
        monday_board_deals=int(_required("MONDAY_BOARD_DEALS")),
        monday_board_work_orders=int(_required("MONDAY_BOARD_WORK_ORDERS")),
        cors_origins=[
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        ],
    )
