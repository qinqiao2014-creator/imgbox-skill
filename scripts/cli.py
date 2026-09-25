"""Unified CLI for multi-provider image generation."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure scripts/ is on sys.path when running as `python scripts/cli.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from providers import get, available, disabled as providers_disabled
from providers.base import guard_overwrite
import config_store


# ---------- configure ----------

def cmd_configure(args: argparse.Namespace) -> None:
    name = args.provider
    if name in providers_disabled():
        raise SystemExit(
            f"❌ provider「{name}」已被禁用：{providers_disabled()[name]}\n"
            f"   ⇒ 恢复须用户显式解禁（编辑 scripts/providers/__init__.py 的 DISABLED 表）。"
        )
    if args.clear:
        if config_store.clear(name):
            print(f"已清除 {name} 的配置：{config_store.config_path(name)}")
        else:
            print(f"{name} 没有已保存的配置，无需清除。")
        return

    cfg = config_store.load(name)
    changed = []

    if args.base_url:
        cfg["baseUrl"] = args.base_url
        changed.append("baseUrl")

    api_key = args.api_key
    if args.update_key:
        # Interactive entry so the key never lands in shell history
        try:
            from getpass import getpass
            api_key = getpass("请输入 API Key（输入不可见）: ").strip()
        except Exception:
            api_key = input("请输入 API Key: ").strip()
        if not api_key:
            print("未输入 Key，配置未更改。")
            return

    if api_key:
        cfg["apiKey"] = api_key
        changed.append("apiKey")

    if not changed:
        print("没有提供要修改的字段。可用：--base-url / --api-key / --update-key / --clear")
        return

    path = config_store.save(name, cfg)
    print(f"已保存 {name} 配置（{', '.join(changed)}）→ {path}")
    print("提示：该文件已在 .gitignore 中，不会进入仓库。")


# ---------- doctor ----------

def cmd_doctor(_: argparse.Namespace) -> None:
    print("配置体检：\n")
    ok_count = 0
    for name in available():
        st = config_store.status(name)
        flag = "OK  " if st["configured"] else "--  "
        print(f"  [{flag}] {name}")
        print(f"        configured : {st['configured']}")
        if st["keySource"]:
            print(f"        key source : {st['keySource']}")
        if st["baseUrl"]:
            print(f"        base url   : {st['baseUrl']}")
        print(f"        config file: {st['configPath']}"
              f"{'' if st['configExists'] else '  (未创建)'}")
        print()
        if st["configured"]:
            ok_count += 1

    dis = providers_disabled()
    if dis:
        print("已禁用：")
        for _n, _r in dis.items():
            print(f"  [xx] {_n}  —— {_r}")
        print()

    print(f"共 {len(available())} 个 provider，{ok_count} 个已配置。")
    if ok_count == 0:
        print("\n还没有任何 provider 配置 Key。")
        print("示例：python scripts/cli.py configure --provider openai "
              "--base-url https://your-relay/v1 --update-key")


# ---------- generate / edit ----------

def _print_result(result) -> None:
    print(f"已保存: {result.path}")
    print(f"provider: {result.provider}   model: {result.model}")
    if result.extra_paths:
        print(f"其余 {len(result.extra_paths)} 张:")
        for extra in result.extra_paths:
            print(f"  - {extra}")
    if result.usage:
        print(f"usage: {result.usage}")


def _seedream_kwargs(args: argparse.Namespace) -> dict:
    """Collect Seedream-specific options; ignored by providers that don't accept them."""
    kw: dict = {}
    if args.image:
        kw["image"] = args.image
    if args.output_format:
        kw["output_format"] = args.output_format
    if args.optimize_mode:
        kw["optimize_mode"] = args.optimize_mode
    if args.background:
        kw["background"] = args.background
    if args.layer_decomposition:
        kw["layer_decomposition"] = True
    if getattr(args, "watermark", False):
        kw["watermark"] = True
    else:
        # 默认无水印（--no-watermark 老 flag 仍兼容，效果等价于默认）
        kw["watermark"] = False
    return kw


def _check_deps(p) -> None:
    """Abort early with a clear install hint if a provider's deps are missing.

    Mirrors api2img's fail-fast philosophy: surface the missing-package problem
    before doing any work, with the exact command to fix it.
    """
    missing = []
    for pkg in getattr(p, "required_packages", []):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        raise SystemExit(
            f"缺少依赖：{', '.join(missing)}\n"
            f"请先安装：pip install -r requirements.txt\n"
            f"（或：pip install {' '.join(missing)}）"
        )


def cmd_generate(args: argparse.Namespace) -> None:
    p = get(args.provider)
    _check_deps(p)
    model = args.model or p.default_model_for_call()
    size = args.size or p.default_size
    sdkw = _seedream_kwargs(args)

    if args.dry_run:
        payload = {
            "provider": args.provider,
            "model": model,
            "prompt": args.prompt,
            "size": size,
            "n": args.n,
            "out": args.out,
            **sdkw,
        }
        print("[dry-run] 将发送以下请求（不会真正调用 API）：")
        print(__import__("json").dumps(payload, ensure_ascii=False, indent=2))
        return

    result = p.generate(
        prompt=args.prompt,
        model=model,
        size=size,
        steps=args.steps,
        seed=args.seed,
        cfg_scale=args.cfg_scale,
        neg_prompt=args.neg_prompt,
        text_mode=args.text_mode,
        n=args.n,
        response_format=args.response_format,
        out=args.out,
        force=args.force,
        **sdkw,
    )
    _print_result(result)

    # 生图后抠图：显式 --removebg 直接跑；交互终端下询问；否则只给提示（不阻塞）
    if getattr(args, "removebg", False):
        _auto_removebg_after_generate(result, args)
    elif sys.stdin.isatty():
        try:
            ans = input("是否对刚生成的图片去除背景（抠图）？[y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans in ("y", "yes", "是"):
            _auto_removebg_after_generate(result, args)
    else:
        print("提示：如需去除背景（抠图），可运行 "
              f"python scripts/cli.py removebg {result.path}")


def cmd_edit(args: argparse.Namespace) -> None:
    p = get(args.provider)
    _check_deps(p)
    model = args.model or p.default_model_for_call()
    size = args.size or p.default_size

    if args.dry_run:
        payload = {
            "provider": args.provider,
            "model": model,
            "image": args.image,
            "mask": args.mask,
            "prompt": args.prompt,
            "size": size,
            "out": args.out,
        }
        print("[dry-run] 将发送以下请求（不会真正调用 API）：")
        print(__import__("json").dumps(payload, ensure_ascii=False, indent=2))
        return

    result = p.edit(
        image=Path(args.image),
        prompt=args.prompt,
        model=model,
        size=size,
        mask=Path(args.mask) if args.mask else None,
        steps=args.steps,
        seed=args.seed,
        cfg_scale=args.cfg_scale,
        neg_prompt=args.neg_prompt,
        text_mode=args.text_mode,
        response_format=args.response_format,
        out=args.out,
        force=args.force,
    )
    _print_result(result)


def _resolve_removebg_out(out: "str | None", p: Path, n: int) -> Path:
    if out:
        op = Path(out)
        if n > 1 or op.is_dir():
            op.mkdir(parents=True, exist_ok=True)
            return op / f"{p.stem}_nobg.png"
        return op
    return p.parent / f"{p.stem}_nobg.png"


def _run_removebg(image_paths, model="u2netp", out=None, force=False):
    """AI 抠图：基于 U²-Net（rembg）去除背景，输出带透明通道的 PNG。

    可复用：命令行 removebg 子命令与「生图后自动抠图」共用同一逻辑。
    """
    try:
        from PIL import Image
        from rembg import new_session, remove
    except ImportError:
        raise SystemExit(
            "缺少依赖：rembg / onnxruntime / Pillow\n"
            "请先安装：pip install -r requirements.txt"
        )

    # 优先使用 skill 内置模型目录（models/u2netp/u2netp.onnx），否则回退 rembg 默认
    skill_root = Path(__file__).resolve().parents[1]
    local_model = skill_root / "models" / "u2netp" / "u2netp.onnx"
    if local_model.exists():
        os.environ.setdefault("U2NET_HOME", str(skill_root))

    try:
        session = new_session(model)
    except Exception as e:
        raise SystemExit(f"加载 rembg 模型失败（{model}）：{e}")

    saved = []
    for img_path in image_paths:
        p = Path(img_path)
        if not p.exists():
            print(f"跳过（文件不存在）: {img_path}")
            continue
        im = Image.open(p).convert("RGB")
        out_im = remove(im, session=session)  # 返回带 alpha 的 PIL.Image (RGBA)
        out_path = _resolve_removebg_out(out, p, len(image_paths))
        guard_overwrite(out_path, force)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_im.save(out_path)
        print(f"已保存: {out_path}  (model: {model})")
        saved.append(out_path)
    return saved


def _auto_removebg_after_generate(result, args) -> None:
    """生图后自动抠图：收集所有输出路径，对每张跑 removebg。

    生图流程里 out 通常已指向原图，故抠图结果一律输出为 <stem>_nobg.png，
    不覆盖原图。
    """
    paths = [result.path] + (result.extra_paths or [])
    print("\n── 自动抠图（去除背景）──")
    _run_removebg(
        paths,
        model=getattr(args, "removebg_model", None) or "u2netp",
        out=None,
        force=args.force,
    )


def cmd_removebg(args: argparse.Namespace) -> None:
    """AI 抠图：基于 U²-Net（rembg）去除背景，输出带透明通道的 PNG。"""
    _run_removebg(args.image, model=args.model or "u2netp", out=args.out, force=args.force)


def cmd_list(_: argparse.Namespace) -> None:
    print("可用生图厂商：\n")
    for name in available():
        p = get(name)
        print(f"  {name}")
        print(f"    模型: {', '.join(p.models)}")
        st = config_store.status(name)
        print(f"    配置: {'已配置' if st['configured'] else '未配置'}")
        print()


# ---------- poster ----------

RATIO_SIZES = {"3:4": "1080x1440", "9:16": "1080x1920", "1:1": "1024x1024"}

def cmd_poster(args: argparse.Namespace) -> None:
    """生成带嵌入式中文文字的竖版海报——一次性把文案传给模型，不拆成背景+叠文字。

    核心教训：文字内容必须放在 prompt 里一起发给文生图模型，不能先生成背景再叠文字。
    """
    ratio = args.ratio
    size = RATIO_SIZES.get(ratio, args.custom_size or "1080x1440")

    # 构建单条完整 prompt
    parts = [f"竖版海报{ratio}比例{size}，{args.style}。"]
    parts.append(f"海报上必须清晰显示以下文字：顶部大字「{args.title}」")
    if args.subtitle:
        parts.append(f"副标题「{args.subtitle}」")

    if args.items:
        parts.append("中部列表：")
        for item in args.items:
            parts.append(f"· {item}")

    parts.append(f"底部：{args.footer or args.title}")
    parts.append("整体深色背景浅色文字，所有中文文字必须清晰可读，间距合理。")
    if getattr(args, "strict_text", False):
        parts.append("只显示以上文字，不要添加任何其他文字、标语、说明或装饰性文字。")

    prompt = " ".join(parts)

    # 调用指定 provider
    p = get(args.provider)
    _check_deps(p)
    model = args.model or p.default_model_for_call()

    result = p.generate(
        prompt=prompt,
        model=model,
        size=size,
        out=args.out,
        force=args.force,
        watermark=False,
    )
    _print_result(result)


# ---------- parser ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imgbox-skill",
        description="统一生图 CLI（多厂商，StepFun / Seedream / 任意 OpenAI 兼容接口）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出可用厂商与配置状态")
    sub.add_parser("doctor", help="检查各厂商配置状态")

    p_conf = sub.add_parser("configure", help="配置某厂商的 base-url / api-key")
    p_conf.add_argument("--provider", required=True)
    p_conf.add_argument("--base-url", default=None, help="OpenAI 兼容 base-url")
    p_conf.add_argument("--api-key", default=None, help="直接写入 Key（会出现在 shell 历史）")
    p_conf.add_argument("--update-key", action="store_true", help="交互式输入 Key（推荐）")
    p_conf.add_argument("--clear", action="store_true", help="清除该厂商配置")

    p_gen = sub.add_parser("generate", help="文生图")
    p_gen.add_argument("prompt")
    p_gen.add_argument("--provider", required=True)
    p_gen.add_argument("--model", default=None)
    p_gen.add_argument("--size", default=None, help="不填则用该厂商默认尺寸")
    p_gen.add_argument("--steps", type=int, default=None)
    p_gen.add_argument("--seed", type=int, default=None)
    p_gen.add_argument("--cfg-scale", type=float, default=None)
    p_gen.add_argument("--neg-prompt", default=None)
    p_gen.add_argument("--text-mode", action="store_true", default=False)
    p_gen.add_argument("--n", type=int, default=1)
    p_gen.add_argument("--response-format", default="b64_json")
    p_gen.add_argument("--image", action="append", default=None,
                       help="参考图（可多次，本地路径会转 base64；Seedream 图生图/多图生图用）")
    p_gen.add_argument("--output-format", default=None, choices=["png", "jpeg"],
                       help="Seedream 输出格式（默认 jpeg）")
    p_gen.add_argument("--optimize-mode", default=None, choices=["standard", "fast"],
                       help="Seedream 提示词优化模式")
    p_gen.add_argument("--background", default=None, choices=["transparent", "opaque"],
                       help="Seedream 背景（图生图场景，仅 5.0 pro）")
    p_gen.add_argument("--layer-decomposition", action="store_true", default=False,
                       help="Seedream 图层拆分（仅 5.0 pro）")
    p_gen.add_argument("--watermark", action="store_true", default=False,
                       help="Seedream 开启「AI生成」水印（默认无水印）")
    p_gen.add_argument("--no-watermark", action="store_true", default=False,
                       help="（已废弃，默认即无水印）保留兼容旧命令")
    p_gen.add_argument("--out", default=None)
    p_gen.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    p_gen.add_argument("--removebg", action="store_true", default=False,
                       help="生图后自动去除背景（抠图），输出透明 PNG（<原名>_nobg.png）")
    p_gen.add_argument("--removebg-model", default="u2netp",
                       help="抠图模型名，默认 u2netp（skill 已内置轻量小模型）")
    p_gen.add_argument("--dry-run", action="store_true", help="只打印请求体，不调用 API")

    p_edit = sub.add_parser("edit", help="图编辑")
    p_edit.add_argument("image")
    p_edit.add_argument("prompt")
    p_edit.add_argument("--provider", required=True)
    p_edit.add_argument("--model", default=None)
    p_edit.add_argument("--size", default=None, help="不填则用该厂商默认尺寸")
    p_edit.add_argument("--mask", default=None, help="蒙版图片路径（局部重绘）")
    p_edit.add_argument("--steps", type=int, default=None)
    p_edit.add_argument("--seed", type=int, default=None)
    p_edit.add_argument("--cfg-scale", type=float, default=None)
    p_edit.add_argument("--neg-prompt", default=None)
    p_edit.add_argument("--text-mode", action="store_true", default=False)
    p_edit.add_argument("--response-format", default="b64_json")
    p_edit.add_argument("--out", default=None)
    p_edit.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    p_edit.add_argument("--dry-run", action="store_true", help="只打印请求体，不调用 API")

    p_rm = sub.add_parser("removebg", help="AI 抠图（rembg / U²-Net）")
    p_rm.add_argument("image", nargs="+", help="输入图片路径（可多张）")
    p_rm.add_argument("--model", default="u2netp",
                      help="rembg 模型名，默认 u2netp（轻量小模型，skill 已内置）")
    p_rm.add_argument("--out", default=None, help="输出路径；多张时作为输出目录")
    p_rm.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")

    p_poster = sub.add_parser("poster", help="生成带嵌入式中文文字的竖版海报（文字随 prompt 一起传给模型）")
    p_poster.add_argument("--title", required=True, help="海报大标题")
    p_poster.add_argument("--subtitle", default=None, help="副标题")
    p_poster.add_argument("--items", nargs="*", default=None, help="中部列表项，每项一条引号包裹")
    p_poster.add_argument("--footer", default=None, help="底部文字（默认同标题）")
    p_poster.add_argument("--style", default="科技感深蓝紫 dark mode，极简留白",
                          help="风格描述，如「科技感深蓝紫 dark mode」「赛博朋克金色光效」")
    p_poster.add_argument("--ratio", default="3:4", choices=["3:4", "9:16", "1:1"],
                          help="画面比例（默认 3:4）")
    p_poster.add_argument("--custom-size", default=None, help="自定义尺寸（如 1024x1024），覆盖 --ratio")
    p_poster.add_argument("--provider", default="stepfun", help="生图厂商（默认 stepfun；seedream 已于 2026-09-25 禁用）")
    p_poster.add_argument("--model", default=None, help="模型名（默认用该厂商的 default）")
    p_poster.add_argument("--out", default=None, help="输出路径")
    p_poster.add_argument("--strict-text", action="store_true",
                          help="严格只出给定文案，禁止模型自行补充任何文字")
    p_poster.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    handlers = {
        "list": cmd_list,
        "doctor": cmd_doctor,
        "configure": cmd_configure,
        "generate": cmd_generate,
        "edit": cmd_edit,
        "removebg": cmd_removebg,
        "poster": cmd_poster,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
