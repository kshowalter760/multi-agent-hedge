import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AgentConfig(StrictModel):
    model: str = "llama3.1:8b"


class Config(StrictModel):
    ollama_host: str = "http://localhost:11434"
    analyst: AgentConfig = Field(default_factory=AgentConfig)
    risk: AgentConfig = Field(default_factory=lambda: AgentConfig(model="qwen2.5:7b"))
    pm: AgentConfig = Field(default_factory=AgentConfig)
    senior: AgentConfig = Field(default_factory=lambda: AgentConfig(model="qwen2.5:7b"))
    senior_approval_enabled: bool = False
    DANGEROUS_ENABLE_REAL_EXECUTION: bool = False
    num_ctx: int = Field(default=16384, ge=512)
    max_output_tokens: int = Field(default=1536, ge=64)
    token_budget: int = Field(default=100000, ge=128)
    wall_clock_seconds: float = Field(default=1800, gt=0)
    timeout_seconds: float = Field(default=600, gt=0)
    concurrency: int = Field(default=1, ge=1, le=16)
    temperature: float = Field(default=0, ge=0, le=2)
    seed: int = 42
    keep_alive: str = "5m"
    retries: int = Field(default=2, ge=0, le=5)
    expiry_hours: float = Field(default=24, gt=0)
    max_data_age_days: int = Field(default=120, ge=0)
    terminal_growth_bound: float = Field(default=0.03, ge=0, le=0.05)
    max_position_size: float = Field(default=0.10, gt=0, le=1)
    max_sector_exposure: float = Field(default=0.30, gt=0, le=1)
    cash_floor: float = Field(default=0.10, ge=0, le=1)
    initial_cash: float = Field(default=100000, gt=0)
    currency: str = "USD"
    data_file: str = "examples/financials.csv"

    @classmethod
    def load(cls, path: Path):
        load_dotenv(path.parent / ".env")
        values = tomllib.loads(path.read_text("utf-8")) if path.exists() else {}
        if os.getenv("OLLAMA_HOST"):
            values["ollama_host"] = os.environ["OLLAMA_HOST"]
        return cls.model_validate(values)
