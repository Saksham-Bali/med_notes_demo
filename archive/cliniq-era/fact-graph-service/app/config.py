import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 5006
    data_dir: Path = Path("/app/data")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "5006")),
            data_dir=Path(os.getenv("DATA_DIR", "/app/data")),
        )
