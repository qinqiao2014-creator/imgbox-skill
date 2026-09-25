"""Provider registry with lazy loading to avoid circular imports."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Dict, List, Type

from .base import BaseProvider

_REGISTRY: Dict[str, Type[BaseProvider]] = {}
_LOADED: List[str] = []

# ★ 2026-09-25 用户指令：「接下来你就不要用火山引擎生图了」——全局禁用火山方舟 Seedream。
#   机器可读禁用态：登记在本表即拒绝 get() / configure（ARK_API_KEY 环境变量兜底也一并挡住）。
#   恢复须用户显式解禁（从本表移除并同步 SKILL.md 说明），不得自行放开。
DISABLED: Dict[str, str] = {
    "seedream": "2026-09-25 用户指令：全局禁用火山引擎生图",
}


def _load(name: str) -> None:
    if name in _LOADED:
        return
    module_path = Path(__file__).parent / f"{name}.py"
    if not module_path.exists():
        return
    mod = import_module(f".{name}", __name__)
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseProvider)
            and obj is not BaseProvider
        ):
            _REGISTRY[obj.name] = obj
    _LOADED.append(name)


def register(provider_cls: Type[BaseProvider]) -> Type[BaseProvider]:
    _REGISTRY[provider_cls.name] = provider_cls
    return provider_cls


def get(name: str) -> BaseProvider:
    if name in DISABLED:
        raise SystemExit(
            f"❌ provider「{name}」已被禁用：{DISABLED[name]}\n"
            f"   ⇒ 确需恢复时，由用户显式解禁（编辑 scripts/providers/__init__.py 的 DISABLED 表）。"
        )
    _load(name)
    if name not in _REGISTRY:
        # Make sure the registry is populated so the error lists real options
        available()
        raise SystemExit(
            f"未知 provider: {name}。可用: {', '.join(sorted(_REGISTRY)) or '（无）'}"
        )
    return _REGISTRY[name]()


def available() -> List[str]:
    """Auto-discover every provider module in this package (drop-in extensibility)."""
    here = Path(__file__).parent
    for module_path in sorted(here.glob("*.py")):
        stem = module_path.stem
        if stem in ("__init__", "base"):
            continue
        _load(stem)
    return sorted(n for n in _REGISTRY if n not in DISABLED)


def disabled() -> Dict[str, str]:
    """已禁用的 provider 及原因（list / doctor 展示用）。"""
    return dict(DISABLED)
