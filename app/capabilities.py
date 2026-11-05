"""Capability + key catalog for the settings UI.

The UI must never hardcode provider names or key names: everything here is
derived from the tool registry, so adding a provider tool automatically adds
its key to the settings page.
"""

from __future__ import annotations

import os
from typing import Any

from app import secrets_store

# Pi model providers worth surfacing first; the store accepts any name.
PI_PROVIDERS: list[dict[str, str]] = [
    {"provider": "anthropic", "label": "Anthropic (Claude)", "env": "ANTHROPIC_API_KEY"},
    {"provider": "openai", "label": "OpenAI", "env": "OPENAI_API_KEY"},
    {"provider": "deepseek", "label": "DeepSeek", "env": "DEEPSEEK_API_KEY"},
    {"provider": "google", "label": "Google Gemini", "env": "GEMINI_API_KEY"},
    {"provider": "openrouter", "label": "OpenRouter", "env": "OPENROUTER_API_KEY"},
    {"provider": "xai", "label": "xAI (Grok)", "env": "XAI_API_KEY"},
    {"provider": "mistral", "label": "Mistral", "env": "MISTRAL_API_KEY"},
    {"provider": "groq", "label": "Groq", "env": "GROQ_API_KEY"},
    {"provider": "moonshot", "label": "Moonshot / Kimi", "env": "MOONSHOT_API_KEY"},
    {"provider": "qwen", "label": "Qwen", "env": "QWEN_TOKEN_PLAN_API_KEY"},
]


def _registry() -> Any:
    import adplus  # noqa: F401 — puts vendor/openmontage on sys.path

    from tools.tool_registry import registry

    registry.discover()
    return registry


_applied: set[str] = set()


def apply_secrets_to_env() -> int:
    """Reconcile this process env with the secret store.

    Deleted keys must disappear from the environment too, otherwise tool
    status checks keep reporting a capability the user just removed.
    """
    stored = secrets_store._read_mirror()  # noqa: SLF001 - single source of truth
    changed = 0
    for name, value in stored.items():
        if name and value and os.environ.get(name) != value:
            os.environ[name] = value
            changed += 1
        _applied.add(name)
    for name in list(_applied - set(stored)):
        os.environ.pop(name, None)
        _applied.discard(name)
        changed += 1
    return changed


def matrix() -> dict[str, Any]:
    reg = _registry()
    summary = reg.provider_menu_summary()
    return {
        "runtimes": summary.get("composition_runtimes") or {},
        "capabilities": [
            {
                "capability": item.get("capability"),
                "configured": item.get("configured"),
                "total": item.get("total"),
                "providers": item.get("providers") or [],
            }
            for item in summary.get("capabilities", [])
            if item.get("total")
        ],
        "warnings": summary.get("runtime_warnings") or [],
    }


# Human-readable vendor names for the settings list: the env var name alone
# tells nobody which service they are about to sign up for.
VENDOR_LABELS = {
    "FAL_KEY": "Fal.ai",
    "ATLASCLOUD_API_KEY": "Atlas Cloud",
    "KLING_API_KEY": "Kling",
    "HEYGEN_API_KEY": "HeyGen",
    "REPLICATE_API_TOKEN": "Replicate",
    "MINIMAX_API_KEY": "MiniMax",
    "MISTRAL_API_KEY": "Mistral",
    "RUNWAY_API_KEY": "Runway",
    "ELEVENLABS_API_KEY": "ElevenLabs",
    "OPENAI_API_KEY": "OpenAI",
    "GEMINI_API_KEY": "Google Gemini",
    "GOOGLE_API_KEY": "Google",
    "AZURE_SPEECH_KEY": "Azure Speech",
    "DOUBAO_API_KEY": "Doubao / Volcengine",
    "VOLCENGINE_ACCESS_KEY": "Volcengine",
    "DASHSCOPE_API_KEY": "Alibaba DashScope",
    "FISH_AUDIO_API_KEY": "fish.audio",
    "LYRIA_API_KEY": "Google Lyria",
    "SUNO_API_KEY": "Suno",
    "PEXELS_API_KEY": "Pexels",
    "PIXABAY_API_KEY": "Pixabay",
    "UNSPLASH_ACCESS_KEY": "Unsplash",
    "BFL_API_KEY": "Black Forest Labs",
    "XAI_API_KEY": "xAI",
    "GROQ_API_KEY": "Groq",
    "OPENROUTER_API_KEY": "OpenRouter",
    "ANTHROPIC_API_KEY": "Anthropic",
    "DEEPSEEK_API_KEY": "DeepSeek",
    "TENCENT_TOKENHUB_API_KEY": "腾讯混元 TokenHub",
    "ARK_API_KEY": "火山方舟 Ark",
    "VOLC_ACCESSKEY": "火山引擎 Access Key",
    "VOLC_SECRETKEY": "火山引擎 Secret Key",
    "LTX_API_KEY": "LTX (Lightricks)",
    "MAI_API_KEY": "MAI (Microsoft)",
    "MAI_ENDPOINT": "MAI Endpoint",
    "MAI_IMAGE_DEPLOYMENT": "MAI 图像部署",
    "BRIA_API_TOKEN": "Bria",
    "CARTESIA_API_KEY": "Cartesia",
    "IDEOGRAM_API_KEY": "Ideogram",
    "INWORLD_API_KEY": "Inworld",
}


def vendor_label(name: str) -> str:
    if name in VENDOR_LABELS:
        return VENDOR_LABELS[name]
    stem = name.replace("_API_KEY", "").replace("_API_TOKEN", "").replace("_TOKEN", "").replace("_KEY", "")
    return stem.replace("_", " ").title() or name


def key_groups() -> list[dict[str, Any]]:
    """Group every key the registry knows about, with what it would unlock."""
    reg = _registry()
    summary = reg.provider_menu_summary()
    buckets: dict[str, dict[str, Any]] = {}

    for offer in summary.get("setup_offers", []):
        for env_name in offer.get("env_vars") or []:
            bucket = buckets.setdefault(
                env_name,
                {
                    "name": env_name,
                    "capabilities": set(),
                    "tools": set(),
                    "instructions": "",
                },
            )
            bucket["capabilities"].add(offer.get("capability"))
            bucket["tools"].add(offer.get("tool"))
            if not bucket["instructions"] and offer.get("install_instructions"):
                bucket["instructions"] = offer["install_instructions"].splitlines()[0]

    for name, tool in reg._tools.items():  # noqa: SLF001 - need raw dependency strings
        for dep in getattr(tool, "dependencies", []) or []:
            if isinstance(dep, str) and dep.startswith("env:"):
                env_name = dep[4:]
                bucket = buckets.setdefault(
                    env_name,
                    {"name": env_name, "capabilities": set(), "tools": set(), "instructions": ""},
                )
                bucket["capabilities"].add(getattr(tool, "capability", None))
                bucket["tools"].add(name)

    configured = secrets_store.configured_names() | {
        k for k in os.environ if k.endswith(("_API_KEY", "_TOKEN", "_SECRET"))
    }
    rows = []
    for name, bucket in buckets.items():
        value = secrets_store.get_secret(name) if name in secrets_store.configured_names() else os.environ.get(name)
        rows.append(
            {
                "name": name,
                "label": vendor_label(name),
                "configured": bool(value),
                "masked": secrets_store.mask(value or ""),
                "capabilities": sorted(c for c in bucket["capabilities"] if c),
                "unlocks": len(bucket["tools"]),
                "instructions": bucket["instructions"],
                "in_keychain": name in secrets_store.configured_names(),
            }
        )
    rows.sort(key=lambda r: (-r["unlocks"], r["name"]))
    return rows


def pi_block() -> dict[str, Any]:
    providers = []
    for item in PI_PROVIDERS:
        value = secrets_store.get_secret(item["env"]) or os.environ.get(item["env"])
        providers.append(
            {
                **item,
                "configured": bool(value),
                "masked": secrets_store.mask(value or ""),
            }
        )
    return {"providers": providers}


def snapshot() -> dict[str, Any]:
    apply_secrets_to_env()
    return {
        "matrix": matrix(),
        "keys": key_groups(),
        "pi": pi_block(),
        "app_data": str(secrets_store.app_data_dir()),
        "keychain": secrets_store.keychain_available(),
    }
