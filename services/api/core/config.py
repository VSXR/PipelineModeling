from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PipelineModeling API"
    model_path: str = "/app/model/weights/model.pkl"
    git_repo_path: str = "/app"
    dvc_remote_path: str = "/dvc-remote"


settings = Settings()
