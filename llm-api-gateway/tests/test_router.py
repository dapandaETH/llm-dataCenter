import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from router import ModelRouter, RouterConfig, ModelConfig


@pytest.fixture
def config():
    return RouterConfig(
        models={
            "glm5": ModelConfig(
                backend_url="http://localhost:8000", display_name="GLM-5"
            ),
            "llama3": ModelConfig(
                backend_url="http://localhost:8001", display_name="Llama 3"
            ),
        }
    )


def test_get_backend_url(config):
    r = ModelRouter(config)
    assert r.get_backend_url("glm5") == "http://localhost:8000"
    assert r.get_backend_url("llama3") == "http://localhost:8001"


def test_get_backend_url_unknown_model(config):
    r = ModelRouter(config)
    with pytest.raises(ValueError, match="Unknown model"):
        r.get_backend_url("unknown")


def test_list_models(config):
    r = ModelRouter(config)
    models = r.list_models()
    assert len(models) == 2
    assert models[0]["id"] == "glm5"
