from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    app_name: str = "PipelineModeling API"
    model_path: str = "/app/model/weights/model.pkl"
    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_model_name: str = "pipeline-model"


settings = Settings()
