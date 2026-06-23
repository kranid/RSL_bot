import os
from typing import Annotated
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode


class TelegramSettings(BaseModel):
    token: str
    valid_content_types: list[str] = ["video", "video_note", "GIF"]


class Database(BaseModel):
    hosts: Annotated[list[str], NoDecode]
    port: int = 5432
    db: str
    user: str
    password: str

    @field_validator('hosts', mode='before')
    @classmethod
    def decode_hosts(cls, v: str) -> list[str]:
        return [x.strip() for x in v.split(',')]
    

class CoordinatorSettings(BaseModel):
    key:str
    url:str
    task_deadline_seconds:int = 30
    min_polling_interval_seconds:float = 0.5
    max_polling_interval_seconds:float = 100


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        from_attributes=True,
        env_file=(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                ".env.template",
            ),
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                ".env",
            ),
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
        env_prefix="CV_BOT__",
    )

    tg:TelegramSettings
    database:Database
    coordinator:CoordinatorSettings


settings = Settings()
