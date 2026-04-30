"""
Multi-model AI routing layer.

Picks the best available model for each task based on which API keys are configured.
Supports: Gemini (free fallback), Claude, GPT-4o, Perplexity.
"""

import base64
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

MODELS = {
    "gemini": "gemini-2.0-flash",
    "claude": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "perplexity": "sonar",
}

# Best model per task — left is preferred, right is fallback
TASK_PREFERENCES = {
    "extract": ["openai", "gemini"],       # Vision/OCR — GPT-4o best at handwriting
    "evaluate": ["gemini", "openai"],      # Grading extracted text — Gemini cheapest
    "practice": ["gemini", "openai"],
    "explain": ["gemini", "perplexity", "openai"],
    "debate": ["gemini", "openai"],
    "read_image": ["openai", "gemini"],
}

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".gif": "image/gif",
}


BILLING_URLS = {
    "gemini": "https://aistudio.google.com/apikey",
    "claude": "https://console.anthropic.com/settings/billing",
    "openai": "https://platform.openai.com/settings/organization/billing",
    "perplexity": "https://www.perplexity.ai/settings/api",
}

HEALTH_PROMPTS = {
    "gemini": "Reply with just the word OK",
    "claude": "Reply with just the word OK",
    "openai": "Reply with just the word OK",
    "perplexity": "Reply with just the word OK",
}


class ModelRouter:
    def __init__(self, skip_health_check=False):
        self.available = {}
        self.health = {}  # {model: {"status": "ok"/"no_credits"/"error", "message": str}}
        self._init_clients()
        if not self.available:
            raise RuntimeError(
                "No AI API keys found. Set at least GEMINI_API_KEY in .env file.\n"
                "Supported: GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, PERPLEXITY_API_KEY"
            )
        if not skip_health_check:
            self._health_check()
        logger.info(f"Available models: {', '.join(self.available.keys())}")

    def _init_clients(self):
        # Gemini
        if os.environ.get("GEMINI_API_KEY"):
            try:
                from google import genai

                self.available["gemini"] = genai.Client(
                    api_key=os.environ["GEMINI_API_KEY"]
                )
                logger.info("Gemini: ready")
            except ImportError:
                logger.warning("google-genai not installed — skipping Gemini")

        # Claude
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic

                self.available["claude"] = anthropic.Anthropic(
                    api_key=os.environ["ANTHROPIC_API_KEY"]
                )
                logger.info("Claude: ready")
            except ImportError:
                logger.warning("anthropic not installed — skipping Claude")

        # OpenAI
        if os.environ.get("OPENAI_API_KEY"):
            try:
                import openai

                self.available["openai"] = openai.OpenAI(
                    api_key=os.environ["OPENAI_API_KEY"]
                )
                logger.info("OpenAI: ready")
            except ImportError:
                logger.warning("openai not installed — skipping OpenAI")

        # Perplexity (OpenAI-compatible API)
        if os.environ.get("PERPLEXITY_API_KEY"):
            try:
                import openai

                self.available["perplexity"] = openai.OpenAI(
                    api_key=os.environ["PERPLEXITY_API_KEY"],
                    base_url="https://api.perplexity.ai",
                )
                logger.info("Perplexity: ready")
            except ImportError:
                logger.warning("openai not installed — skipping Perplexity")

    def _health_check(self):
        """Test each API key with a trivial call. Remove dead ones."""
        logger.info("Running startup health check on all API keys...")
        dead = []
        for model in list(self.available.keys()):
            try:
                if model == "gemini":
                    self._call_gemini(HEALTH_PROMPTS["gemini"], None)
                elif model == "claude":
                    self._call_claude(HEALTH_PROMPTS["claude"], None)
                elif model == "openai":
                    self._call_openai(HEALTH_PROMPTS["openai"], None)
                elif model == "perplexity":
                    self._call_perplexity(HEALTH_PROMPTS["perplexity"])
                self.health[model] = {"status": "ok", "message": "Working"}
                logger.info(f"  {model}: OK")
            except Exception as e:
                err = str(e).lower()
                if "quota" in err or "credit" in err or "balance" in err or "billing" in err:
                    self.health[model] = {
                        "status": "no_credits",
                        "message": f"No credits. Refill at {BILLING_URLS.get(model, '')}",
                    }
                    logger.warning(f"  {model}: NO CREDITS — disabling")
                else:
                    self.health[model] = {"status": "error", "message": str(e)[:200]}
                    logger.warning(f"  {model}: ERROR — {str(e)[:100]}")
                dead.append(model)

        for model in dead:
            del self.available[model]

        if not self.available:
            raise RuntimeError(
                "All API keys failed health check! At least one needs credits.\n"
                + "\n".join(f"  {m}: {self.health[m]['message']}" for m in dead)
            )

    def pick(self, task):
        """Pick the best available model for a task."""
        prefs = TASK_PREFERENCES.get(task, ["gemini"])
        for model in prefs:
            if model in self.available:
                return model
        return next(iter(self.available))

    def status(self):
        """Return which models are available, dead, and task assignments."""
        assignments = {}
        for task in TASK_PREFERENCES:
            assignments[task] = self.pick(task)
        return {
            "available": list(self.available.keys()),
            "health": self.health,
            "assignments": assignments,
        }

    def call(self, task, prompt, images=None):
        """
        Call the best available model for a task.

        Args:
            task: 'evaluate', 'practice', 'explain', or 'read_image'
            prompt: text prompt
            images: list of file paths or (base64_data, mime_type) tuples

        Returns: model response text
        """
        model = self.pick(task)
        logger.info(f"Task '{task}' → {model}")

        try:
            return self._dispatch(model, prompt, images)
        except Exception as e:
            err = str(e).lower()
            if "quota" in err or "credit" in err or "balance" in err or "billing" in err:
                logger.warning(f"{model} ran out of credits mid-session! Falling back...")
                self.health[model] = {
                    "status": "no_credits",
                    "message": f"Credits exhausted. Refill at {BILLING_URLS.get(model, '')}",
                }
                del self.available[model]
                if not self.available:
                    raise
                # Retry with next best model
                fallback = self.pick(task)
                logger.info(f"Falling back to {fallback}")
                return self._dispatch(fallback, prompt, images)
            raise

    def _dispatch(self, model, prompt, images):
        if model == "gemini":
            return self._call_gemini(prompt, images)
        elif model == "claude":
            return self._call_claude(prompt, images)
        elif model == "openai":
            return self._call_openai(prompt, images)
        elif model == "perplexity":
            return self._call_perplexity(prompt)
        raise RuntimeError(f"No handler for model: {model}")

    def _prepare_images(self, images):
        """Convert image paths to (base64, mime_type) tuples."""
        if not images:
            return []
        result = []
        for img in images:
            if isinstance(img, tuple):
                result.append(img)
            elif isinstance(img, (str, Path)):
                path = Path(img)
                mime = MIME_MAP.get(path.suffix.lower(), "image/jpeg")
                with open(path, "rb") as f:
                    b64 = base64.standard_b64encode(f.read()).decode()
                result.append((b64, mime))
        return result

    def _call_gemini(self, prompt, images):
        client = self.available["gemini"]
        parts = []
        for b64, mime in self._prepare_images(images):
            parts.append({"inline_data": {"mime_type": mime, "data": b64}})
        parts.append({"text": prompt})
        response = client.models.generate_content(
            model=MODELS["gemini"],
            contents=[{"role": "user", "parts": parts}],
        )
        return response.text

    def _call_claude(self, prompt, images):
        client = self.available["claude"]
        content = []
        for b64, mime in self._prepare_images(images):
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": mime, "data": b64},
                }
            )
        content.append({"type": "text", "text": prompt})
        response = client.messages.create(
            model=MODELS["claude"],
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text

    def _call_openai(self, prompt, images):
        client = self.available["openai"]
        content = []
        for b64, mime in self._prepare_images(images):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            )
        content.append({"type": "text", "text": prompt})
        response = client.chat.completions.create(
            model=MODELS["openai"],
            messages=[{"role": "user", "content": content}],
            max_tokens=4096,
        )
        return response.choices[0].message.content

    def _call_perplexity(self, prompt):
        """Perplexity — text only, no image support."""
        client = self.available["perplexity"]
        response = client.chat.completions.create(
            model=MODELS["perplexity"],
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
