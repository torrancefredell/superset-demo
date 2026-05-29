from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    devin_api_token: str = ""
    devin_org_id: str = ""
    devin_api_base_url: str = "https://api.devin.ai/v3"
    github_webhook_secret: str = ""
    github_token: str = ""
    target_repo_url: str = "https://github.com/torrancefredell/superset"

    model_config = {"env_file": ".env"}


settings = Settings()
