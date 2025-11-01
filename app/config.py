# from pydantic V2+ the BaseSettings Class has been moved to
# pydantic_settings package this class automattically collects
# data from the '.env' file with it being set as the config

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # database info
    database_host: str
    database_port: int
    database_password: str
    database_user: str
    database_name: str
    # jwt info
    secret_key: str
    algorithm: str
    access_token_expire_time: int
    # email info
    email_username: str
    email_password: str
    email_from: str
    email_port: int
    email_server: str
    # base url
    base_url:str
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()