import yaml
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelConfig:
    backend_url: str
    display_name: str


@dataclass
class RouterConfig:
    models: dict[str, ModelConfig] = field(default_factory=dict)


class ModelRouter:
    def __init__(self, config: RouterConfig):
        self.config = config

    def get_backend_url(self, model: str) -> str:
        model_cfg = self.config.models.get(model)
        if not model_cfg:
            raise ValueError(f"Unknown model: {model}")
        return model_cfg.backend_url

    def list_models(self) -> list[dict[str, Any]]:
        return [
            {
                "id": model_id,
                "object": "model",
                "created": 1677610602,
                "owned_by": "local",
                "display_name": cfg.display_name,
            }
            for model_id, cfg in self.config.models.items()
        ]

    @classmethod
    def from_yaml(cls, path: str) -> "ModelRouter":
        with open(path) as f:
            data = yaml.safe_load(f)
        models = {}
        for model_id, cfg in data.get("models", {}).items():
            models[model_id] = ModelConfig(
                backend_url=cfg["backend_url"],
                display_name=cfg.get("display_name", model_id),
            )
        return cls(RouterConfig(models=models))


def load_router() -> ModelRouter:
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    return ModelRouter.from_yaml(config_path)
