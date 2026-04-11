# from pydantic V2+ the BaseSettings Class has been moved to
# pydantic_settings package this class automattically collects
# data from the '.env' file with it being set as the config

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # database info
    database_host: str
    database_port: int
    database_password: str
    database_user: str
    database_name: str
    # SQLAlchemy async pool tuning
    db_pool_size: int = 60
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    # jwt info
    secret_key: str
    algorithm: str
    access_token_expire_time: int
    refresh_token_expire_days: int = 7
    # email info
    email_username: str
    email_password: str
    email_from: str
    email_port: int
    email_server: str
    # base url
    base_url:str
    # posts media folder
    media_folder:str
    # maximum edit time
    max_edit_time:int
    # redis config
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    # azure blob storage
    azure_storage_connection_string: str = ""
    azure_storage_account_name: str = ""
    # rate limiting — max hits and window (seconds) per endpoint
    rl_login_max: int = 5
    rl_login_window: int = 300
    rl_signup_max: int = 3
    rl_signup_window: int = 3600
    rl_forgot_password_max: int = 3
    rl_forgot_password_window: int = 3600
    rl_reset_password_max: int = 5
    rl_reset_password_window: int = 300
    rl_refresh_max: int = 10
    rl_refresh_window: int = 60
    rl_change_password_max: int = 3
    rl_change_password_window: int = 3600
    rl_reset_password_auth_max: int = 5
    rl_reset_password_auth_window: int = 300
    rl_comment_max: int = 10
    rl_comment_window: int = 60
    rl_create_post_max: int = 5
    rl_create_post_window: int = 60
    rl_follow_max: int = 20
    rl_follow_window: int = 60
    # observability toggles
    otel_console_exporter_enabled: bool = False
    observability_log_enabled: bool = True
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

settings = Settings()