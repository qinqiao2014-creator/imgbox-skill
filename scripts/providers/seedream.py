"""Seedream provider (Volcengine doubao-seedream-5-0-pro).

Full parameter coverage aligned with the official Volcengine Seedream API:
text-to-image, image-to-image (reference images), layer decomposition,
transparent background, prompt optimization, and multi-image results.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_store import get_api_key, load as load_cfg
from .base import BaseProvider, ImageResult, guard_overwrite


NAME = "seedream"
MODELS = [
    "doubao-seedream-5-0-pro-260628",
]
DEFAULT_MODEL = "doubao-seedream-5-0-pro-260628"
API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

# ---------- 每日硬配额（2026-09-25 用户指令写死，任何实例不得绕过） ----------
# 火山方舟 Seedream 账号每日额度 20 张，每天 0 点重置。
# 当日用量达到 20 张后，任何生图请求直接拒绝：不犹豫、不建议重试、不换参数绕过。
# 背景：2026-09-25 曾批量出图一次性烧穿当天额度，用户立此规矩——
#       限额场景一次只出一张，等用户确认再出下一张。
DAILY_LIMIT = 20
QUOTA_FILE = (
    Path(__file__).resolve().parents[2] / "config" / "providers" / "seedream_quota.json"
)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _quota_state() -> Dict[str, Any]:
    """读取当日配额状态；记账文件缺失/损坏/跨天时视为新的一天（从零开始）。"""
    today = _today()
    try:
        if QUOTA_FILE.exists():
            data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return {"date": today, "used": int(data.get("used", 0))}
    except Exception:
        pass
    return {"date": today, "used": 0}


def _check_quota() -> Dict[str, Any]:
    """API 调用前的配额闸门：当日已用 ≥ 20 张 → 直接拒绝退出，不发任何请求。"""
    state = _quota_state()
    if state["used"] >= DAILY_LIMIT:
        raise SystemExit(
            f"❌ Seedream 今日额度已用完（{state['used']}/{DAILY_LIMIT}，{state['date']}）。\n"
            f"   每日 0 点重置，明天再来；急用请改用 stepfun 或 openai。\n"
            f"   （上限由用户指令写死在 scripts/providers/seedream.py，任何实例不得绕过。）"
        )
    return state


def _consume_quota(n: int = 1) -> None:
    """API 已计费后记账：按实际生成张数累加当日用量。"""
    state = _quota_state()
    state["used"] += n
    QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUOTA_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def quota_status() -> Dict[str, Any]:
    """对外暴露当日配额余量（list / doctor 展示用，不触发任何请求）。"""
    state = _quota_state()
    return {
        "date": state["date"],
        "used": state["used"],
        "limit": DAILY_LIMIT,
        "remaining": max(DAILY_LIMIT - state["used"], 0),
        "exhausted": state["used"] >= DAILY_LIMIT,
    }


def _api_key() -> str:
    key = get_api_key(NAME)
    if not key:
        raise SystemExit(
            "未配置 Seedream API Key（或仍是占位符）。\n"
            "运行：python scripts/cli.py configure --provider seedream --api-key <你的Key>"
        )
    return key


def _endpoint() -> str:
    cfg = load_cfg(NAME)
    return cfg.get("endpoint") or os.environ.get("SEEDREAM_ENDPOINT", "ep-20260901141453-x7wsb")


def _out_dir() -> str:
    cfg = load_cfg(NAME)
    return cfg.get("outDir") or os.environ.get("SEEDREAM_OUT_DIR", "output")


def _to_image_field(images: Optional[List[str]]) -> Optional[List[str]]:
    """Reference images: local file -> base64 data URL, otherwise kept as-is (URL)."""
    if not images:
        return None
    out: List[str] = []
    for img in images:
        p = Path(img)
        if p.exists():
            mime = mimetypes.guess_type(p.name)[0] or "image/png"
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            out.append(f"data:{mime};base64,{b64}")
        else:
            out.append(img)  # treat as URL
    return out


def _build_body(
    prompt: str,
    model: str,
    size: str,
    response_format: str,
    watermark: bool,
    output_format: str,
    image: Optional[List[str]],
    optimize_mode: Optional[str],
    background: Optional[str],
    layer_decomposition: bool,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": response_format,
        "output_format": output_format,
        "watermark": watermark,
        "stream": False,
    }
    imgs = _to_image_field(image)
    if imgs:
        body["image"] = imgs
    if optimize_mode:
        body["optimize_prompt_options"] = {"mode": optimize_mode}
    if background:
        body["background"] = background
    if layer_decomposition:
        body["layer_decomposition"] = True
    return body


def _ensure_transparent_refs(images: Optional[List[str]]) -> List[str]:
    """Seedream 5.0 pro `background: transparent` 要求输入图本身带透明通道。

    若传入的本地参考图不透明，自动用内置 rembg(u2netp) 转成透明临时 PNG，
    使「原生透明生图」流水线开箱即用。已透明的图直接复用，不重复处理。
    """
    if not images:
        return []
    try:
        from PIL import Image
        from rembg import new_session, remove
    except ImportError:
        print("提示：未安装 rembg/Pillow，无法自动把参考图转透明；"
              "请传入已透明的 PNG 或先 `pip install -r requirements.txt`。")
        return images

    session = new_session("u2netp")
    out: List[str] = []
    for img in images:
        p = Path(img)
        if not p.exists():
            out.append(img)  # 当作 URL 透传
            continue
        im = Image.open(p)
        has_alpha = im.mode == "RGBA" and im.getextrema()[-1][0] < 255
        if has_alpha:
            out.append(img)
            continue
        tmp = p.parent / f".{p.stem}_transparent.png"
        remove(im.convert("RGB"), session=session).save(tmp)
        out.append(str(tmp))
    return out


class SeedreamProvider(BaseProvider):
    name = NAME
    models = MODELS
    default_model = "doubao-seedream-5-0-pro-260628"
    default_size = "2K"

    def default_model_for_call(self) -> str:
        # Volcengine Ark routes calls through a user-provisioned endpoint id
        # (ep-...), not the bare model name. Default to the configured endpoint.
        return _endpoint()

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        size: str = "2K",
        watermark: bool = True,
        out: Optional[str] = None,
        force: bool = False,
        image: Optional[List[str]] = None,
        output_format: str = "jpeg",
        optimize_mode: Optional[str] = None,
        background: Optional[str] = None,
        layer_decomposition: bool = False,
        response_format: str = "url",
        **_: Any,
    ) -> ImageResult:
        # 每日硬配额闸门：在任何 API 调用之前检查，超限直接拒绝
        _check_quota()
        endpoint = model or _endpoint()
        # 原生透明生图要求参考图本身透明：自动把不透明参考图转透明
        if background == "transparent" and image:
            image = _ensure_transparent_refs(image)
        body = _build_body(
            prompt, endpoint, size, response_format, watermark,
            output_format, image, optimize_mode, background, layer_decomposition,
        )

        try:
            req_obj = urllib.request.Request(API_URL,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {_api_key()}",
                    "Content-Type": "application/json",
                },
                method="POST")
            with urllib.request.urlopen(req_obj, timeout=300) as r:
                raw = r.read()
                if len(raw) != int(r.headers.get("Content-Length", len(raw))):
                    raise SystemExit("Seedream 响应被截断（IncompleteRead），请重试。")
                resp = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            raise SystemExit(f"API 错误 {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise SystemExit(f"网络错误: {e.reason}")

        if "data" not in resp or not resp["data"]:
            raise SystemExit(f"返回异常: {json.dumps(resp, ensure_ascii=False)}")

        # API 已计费：按实际返回张数扣减当日配额（硬配额 20/天）
        _consume_quota(len(resp["data"]))

        # Multi-image results (layer decomposition / multi-image gen) -> save all.
        data = resp["data"]
        ext = ".png" if output_format == "png" else ".jpeg"
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_dir = _out_dir()
        paths: List[Path] = []

        for i, item in enumerate(data):
            if out and len(data) == 1:
                out_path = Path(out)
            elif out:
                stem = Path(out).stem
                parent = Path(out).parent
                suffix = Path(out).suffix or ext
                out_path = parent / f"{stem}_{i+1}{suffix}"
            else:
                out_path = Path(out_dir) / f"seedream_{ts}_{i+1}{ext}"

            guard_overwrite(out_path, force)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            if item.get("b64_json"):
                out_path.write_bytes(base64.b64decode(item["b64_json"]))
            elif item.get("url"):
                urllib.request.urlretrieve(item["url"], out_path)
            else:
                raise SystemExit("返回项缺少 url 或 b64_json。")
            paths.append(out_path)

        return ImageResult(
            path=paths[0],
            provider=NAME,
            model=endpoint,
            usage=resp.get("usage"),
            extra_paths=paths[1:] if len(paths) > 1 else None,
        )

    def edit(self, image: Path, prompt: str, **_: Any) -> ImageResult:
        raise SystemExit(
            "Seedream 暂不支持 OpenAI 风格的 mask 编辑。\n"
            "如需基于参考图的图生图，请用 generate --provider seedream --image <参考图路径或URL>"
        )
