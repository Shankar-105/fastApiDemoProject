# from pydantic V2+ the BaseSettings Class has been moved to
# pydantic_settings package this class automattically collects
# data from the '.env' file with it being set as the config

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_host: str
    database_port: int
    database_password: str
    database_user: str
    database_name: str
    secret_key: str
    algorithm: str
    access_token_expire_time: int

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()