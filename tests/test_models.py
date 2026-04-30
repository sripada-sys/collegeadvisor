"""Tests for models.py — ModelRouter, task dispatch, fallback."""

import os
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

# Pre-mock the google.genai module since it does lazy imports
_mock_genai = MagicMock()
sys.modules.setdefault("google.genai", _mock_genai)
sys.modules.setdefault("google", MagicMock())


class TestModelRouterInit:
    def test_no_keys_raises(self, monkeypatch):
        """Router raises if no API keys are set."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        from importlib import reload
        import models
        reload(models)

        with pytest.raises(RuntimeError, match="No AI API keys found"):
            models.ModelRouter()

    def test_gemini_init(self, monkeypatch):
        """Gemini client is created when key is set."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        from importlib import reload
        import models
        reload(models)
        router = models.ModelRouter(skip_health_check=True)
        assert "gemini" in router.available

    def test_openai_init(self, monkeypatch):
        """OpenAI client is created when key is set."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)
            assert "openai" in router.available

    def test_skip_health_check(self, monkeypatch):
        """skip_health_check=True doesn't call APIs."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)
            assert router.health == {}


class TestTaskPicking:
    def test_pick_preferred_model(self, monkeypatch):
        """pick() returns the first available preferred model for a task."""
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with patch("openai.OpenAI") as mock_oi:
            mock_oi.return_value = MagicMock()

            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)

            # extract prefers openai
            assert router.pick("extract") == "openai"
            # evaluate prefers gemini
            assert router.pick("evaluate") == "gemini"

    def test_pick_fallback(self, monkeypatch):
        """If preferred model not available, falls back."""
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with patch("openai.OpenAI") as mock_oi:
            mock_oi.return_value = MagicMock()
            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)

            # evaluate prefers gemini but only openai available
            assert router.pick("evaluate") == "openai"


class TestStatus:
    def test_status_format(self, monkeypatch):
        """status() returns expected structure."""
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with patch("openai.OpenAI") as mock_oi:
            mock_oi.return_value = MagicMock()
            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)

            status = router.status()
            assert "available" in status
            assert "health" in status
            assert "assignments" in status
            assert "extract" in status["assignments"]


class TestImagePreparation:
    def test_prepare_images_from_path(self, monkeypatch, tmp_path):
        """_prepare_images converts file paths to base64 tuples."""
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with patch("openai.OpenAI") as mock_oi:
            mock_oi.return_value = MagicMock()
            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)

            img = tmp_path / "test.jpg"
            img.write_bytes(b"\xff\xd8\xff\xe0test data")

            result = router._prepare_images([str(img)])
            assert len(result) == 1
            b64, mime = result[0]
            assert mime == "image/jpeg"
            assert len(b64) > 0

    def test_prepare_images_tuple_passthrough(self, monkeypatch):
        """_prepare_images passes tuples through unchanged."""
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with patch("openai.OpenAI") as mock_oi:
            mock_oi.return_value = MagicMock()
            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)

            result = router._prepare_images([("base64data", "image/png")])
            assert result == [("base64data", "image/png")]

    def test_prepare_images_none(self, monkeypatch):
        """_prepare_images handles None."""
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with patch("openai.OpenAI") as mock_oi:
            mock_oi.return_value = MagicMock()
            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)
            assert router._prepare_images(None) == []


class TestCallDispatch:
    def test_call_openai(self, monkeypatch):
        """call() routes to OpenAI and returns text."""
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test response"
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)

            result = router.call("extract", "test prompt")
            assert result == "test response"

    def test_call_fallback_on_quota(self, monkeypatch):
        """If primary model hits quota, falls back to next."""
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        mock_openai = MagicMock()

        # OpenAI works
        mock_oi_response = MagicMock()
        mock_oi_response.choices = [MagicMock()]
        mock_oi_response.choices[0].message.content = "fallback response"
        mock_openai.chat.completions.create.return_value = mock_oi_response

        with patch("openai.OpenAI", return_value=mock_openai):
            from importlib import reload
            import models
            reload(models)
            router = models.ModelRouter(skip_health_check=True)

            # Make gemini raise quota error
            router.available["gemini"] = MagicMock()
            router.available["gemini"].models.generate_content.side_effect = Exception("quota exceeded")

            # evaluate prefers gemini, should fall back to openai
            result = router.call("evaluate", "test")
            assert result == "fallback response"
            assert "gemini" not in router.available
