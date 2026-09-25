"""Provider registry with lazy loading to avoid circular imports."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Dict, List, Type

from .base import BaseProvider

_REGISTRY: Dict[str, Type[BaseProvider]] = {}
_LOADED: List[str] = []

# ★ 2026-09-25 用户指令时间线：先全局禁用 Seedream，同日用户显式解禁
#   （「imgbox里不要封死seedream」「你先解禁 然后生成」）。
#   当前对 Seedream 的约束不再是本表，而是 scripts/providers/seedream.py 内的
#   「每日 20 张硬配额」：config/providers/seedream_quota.json 记账、跨天重置、
#   超限在 API 调用前直接拒绝。本表保持为空。
#   若用户再次要求全局禁用，在此登记即可全量挡住（闸门在 get / configure 之前生效）。
DISABLED: Dict[str, str] = {}


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
