---
name: 百宝箱生图
description: >
  聚合多家生图模型 + AI 抠图的一站式入口（百宝箱）：内置 StepFun / 火山方舟 Seedream（★ 2026-09-25 起已禁用），
  支持任意 OpenAI 兼容生图接口，以及基于 U²-Net 的本地 AI 抠图。
  当用户要生成、编辑、修改图片（概念图、海报、宣传物料、展位视觉、产品 mockup），
  或说"生成图片 / 出图 / 画图 / 用 seedream / 用 stepfun / 抠图 / 去背景"时优先调用本 skill。
  配置内嵌在 skill 目录内，不散落用户根目录，开箱即用。
---

# 百宝箱生图 — 多厂商统一生图

一个 CLI 接多家生图 API。换厂商 = 换配置，不换代码。

## 优先级

用户要生成/编辑位图时，**优先用本 skill**，除非他明确点名另一个 provider 或工具。

## 三个 provider

| provider | 说明 | 依赖 |
|---|---|---|
| `stepfun` | StepFun Step Plan（OpenAI 兼容），支持生图 + 图编辑 | `pip install openai httpx` |
| `seedream` | 火山方舟 doubao-seedream-5-0-pro，支持生图。**★ 2026-09-25 起已全局禁用**（见下方禁用公告） | 无（纯标准库） |
| `openai` | **通用钥匙**：任意 OpenAI 兼容生图接口，填 base-url 即用 | `pip install openai httpx` |
| `removebg` | **AI 抠图**：U²-Net（rembg），本地运行，输出透明 PNG | `pip install rembg onnxruntime pillow` |

> `openai` 是"集成各大生图公司"的关键：只要对方提供 OpenAI 兼容的
> `/images/generations` `/images/edits`，填个 base-url 就能接，不用写新代码。

## ★ 禁用公告（2026-09-25 用户指令）

**「接下来你就不要用火山引擎生图了。」**——火山方舟 Seedream 通道自 2026-09-25 起**全局禁用**：

- `scripts/providers/__init__.py` 的 `DISABLED` 表已列入 `seedream`：`generate` / `edit` / `configure` 三条命令都会**直接拒绝并退出**；环境变量 `ARK_API_KEY` 兜底同样被挡（闸门在 provider 实例化之前生效）。
- 恢复使用**必须由用户显式解禁**（从 `DISABLED` 表移除并重新提交），任何实例不得自行恢复。
- 生图需求请改用 `stepfun`，或用 `openai` 填 base-url 接任意 OpenAI 兼容厂商（速查表见 `references/vendors.md`）。

## 开箱即用（3 步）

### 1. 装依赖（只 stepfun / openai 需要）

```bash
pip install -r requirements.txt
```

> 缺依赖时 `generate` / `edit` 会直接报错并提示这条安装命令，无需手动排查。

### 2. 配置（关键一步）

```bash
# 通用 OpenAI 兼容接口（推荐交互式输入，Key 不进 shell 历史）
python scripts/cli.py configure --provider openai \
  --base-url https://your-relay/v1 --update-key

# StepFun
python scripts/cli.py configure --provider stepfun --update-key

# Seedream
# python scripts/cli.py configure --provider seedream --update-key
```

其他配置操作：

```bash
python scripts/cli.py configure --provider openai --api-key sk-xxx   # 直接写入（会留 shell 历史）
python scripts/cli.py configure --provider openai --clear            # 清除配置
python scripts/cli.py doctor                                          # 体检：谁配了、谁没配
```

配置写在 skill 内的 `config/providers/<name>.json`，已在 `.gitignore` 里，**不会进仓库**。
占位符模板 `config/providers/<name>.example.json` 随仓库发布，供你照格式填写；真实配置由 `configure` 命令生成。
也支持环境变量回退：`STEPFUN_API_KEY` / `ARK_API_KEY` / `OPENAI_API_KEY`。

> 不要去动用户已有的 `OPENAI_API_KEY` / `OPENAI_BASE_URL`，本 skill 用自己独立的配置。

### 3. 出图

```bash
# 文生图
python scripts/cli.py generate "一只赛博朋克风格的广交会吉祥物" --provider stepfun

# 图编辑（改背景、换风格、去掉某个东西）
python scripts/cli.py edit "input.png" "把背景换成安静的影棚，保留主体" --provider openai

# 局部重绘（有蒙版时）
python scripts/cli.py edit "input.png" "只把蒙版区域换成鲜花" --mask "mask.png" --provider openai

# 只校验参数不真调 API
python scripts/cli.py generate "test" --provider openai --dry-run

# AI 抠图（去除背景，输出带透明通道的 PNG）
python scripts/cli.py removebg photo.png --out photo_nobg.png
python scripts/cli.py removebg a.png b.png c.png --out nobg/          # 批量抠图到目录
```

### 4. 生成竖版海报（带嵌入式中文文字）

**核心原则**：文字内容必须一次性放进 prompt 传给模型，不能分两步（先生背景、再叠文字）。
这是此前踩过的坑——背景生成了再 PIL 叠文字，效果远不如一次性传给 Seedream。

```bash
# 基础用法（默认 3:4、stepfun）
python scripts/cli.py poster --title "MCN Studio Skill" --subtitle "内容运营全自动化流水线"   --items "采集:5平台 下载+转写+评论+数据" "分析:Agent爆款拆解 情绪曲线 仿写同款"   --footer "MCN Studio Skill"

# 9:16 海报（适合手机端分享）
python scripts/cli.py poster --title "不是下载器" --subtitle "是内容工厂"   --items "纯Python实现:30+脚本 零第三方依赖" "零浏览器自动化:项目Firefox读Cookie 不封号"   --style "赛博朋克金色光效 dark mode" --ratio "9:16" --force

# 全参数
python scripts/cli.py poster   --title "大标题"   --subtitle "副标题"   --items "标签1:描述文字" "标签2:描述文字"   --footer "底部品牌名"   --style "科技感深蓝紫 dark mode，数字光流粒子"   --ratio "3:4"   --provider stepfun   --force
```

### ★ 出图后必须自检：文字到底上没上去

**不要出完图就直接交付。** 文生图模型偶发「只出背景、不出文字」或「文字串行、缺字」，
必须亲眼验一遍再给用户（这是踩过的坑：曾连出多版纯背景图被用户当场抓包）。

标准自检动作（把 6 张缩成一个总览图，一次看完，省 token）：

```python
from PIL import Image
from pathlib import Path
names = ["poster_01", "poster_02", "poster_03"]
w, h = 340, 604                     # 9:16 缩略尺寸
sheet = Image.new("RGB", (w*len(names)+20, h+20), (24,24,28))
for i, n in enumerate(names):
    im = Image.open(f"{n}.png").convert("RGB").resize((w, h), Image.LANCZOS)
    sheet.paste(im, (10+i*(w+10), 10))
sheet.save("/tmp/poster_sheet.png")  # 缩略图写临时目录，别落在工作区
```

然后逐条核对：
1. **大标题 / 副标题在不在**，字有没有缺笔画、错字、乱码；
2. **每一条 `--items` 是否都出现了**（模型有时会漏掉中间某条）；
3. **有没有模型自己加戏** —— 它常自作主张补一列解释小字、加标语、加数字。
   文案要严格可控时，加 `--strict-text`（会向模型声明「只显示以上文字，不要添加任何其他文字」）；
4. 最挤的那张（条目最多）单独放大裁切再确认一遍。

**发现漏字或加戏 → 直接重跑那张**，不要靠修图补字。

## 生图后可选抠图（removebg 一条龙）

生图（或图编辑）完成后，**用户可以选择顺手抠图**，无需另开命令：
三档选择机制（按运行环境自动适配，绝不阻塞）：

1. **显式 flag**：`generate ... --removebg` → 生图后自动对每张结果跑本地 U²-Net 抠图，
   输出 `<原名>_nobg.png`（透明 PNG），**不覆盖原图**。可加 `--removebg-model u2netp` 换模型。
2. **交互终端询问**：在真实终端（TTY）里跑 `generate` 且没加 `--removebg` 时，
   会问一句「是否对刚生成的图片去除背景（抠图）？[y/N]」，输入 y 即抠。
3. **非交互只提示**：Agent / 管道等非 TTY 环境不询问，仅在结尾打印一行
   `提示：如需去除背景（抠图），可运行 python scripts/cli.py removebg <路径>`，把选择权交给你。

```bash
# 生图并直接抠图（一条命令出透明 PNG）
python scripts/cli.py generate "一只广交会吉祥物" --provider stepfun --removebg

# 等价的两步（手动）：先生图、再抠图
python scripts/cli.py generate "一只广交会吉祥物" --provider stepfun --out mascot.jpeg
python scripts/cli.py removebg mascot.jpeg
```

> 抠图是**本地运行**（rembg + U²-Net），不消耗 API、不上传图片、无额外费用。
> 与 Seedream `--background transparent` 原生透明不同：本功能是对**已生成的任意图片**后处理抠图，
> 两者互补——需要「同角色 + 原生透明」用 `--background transparent`，只是想给现有图去背景就用 `--removebg`。

## 隐私：上传用户图片前必须确认

编辑/修改会**把用户图片上传到第三方 API**。在第一次执行 `edit` 前，
暂停并向用户确认（中文对话用下面这句原话）：

> 提示：你上传的图片可能会被第三方 API 获取，请注意自己的信息安全。请回复确认继续，我再上传图片进行修改。

确认后本次任务不再重复提示，除非用户再次问起隐私。
不要为 prompt、图片路径、Key、API 响应创建额外本地日志。

## 可靠性：生图很慢，别误判失败

- 单张生图起手 **5 分钟（300000 ms）** 超时。
- 超时后按 **5 → 8 → 11 → 14 → 17 分钟** 递增重试，最多 5 次。
- **shell 超时 ≠ 生成失败**：先去 `--out` 指定路径和 `output/` 看有没有新文件。
- 如果超时后文件出现了，直接接着用，不要重跑同一个 prompt。
- 重试前先确认没有残留的 Python 进程在跑。
- 5 次都超时就停下，让用户检查 relay 端点、上游厂商或网络。

## Prompt 组织方式

把用户意图整理成结构化 prompt 再发送（别原样丢一句话进去）：

```text
Use case: <photorealistic-natural | product-mockup | ui-mockup | illustration-story | stylized-concept | logo-brand | precise-object-edit>
Asset type: <用在哪>
Primary request: <用户要什么>
Style/medium: <照片 / 插画 / 3D ...>
Composition/framing: <广角 / 特写 / 居中 ...>
Lighting/mood: <如相关>
Text (verbatim): "<画面里要出现的确切文字>"
Constraints: <必须保留 / 必须避免>
Avoid: no watermark, no unintended text
```

## 工作流

1. 首次生成前先跑 `doctor` 确认配置就绪。
2. `edit` 前走完上面的一次性上传确认。
3. 按 Prompt 模板整理 prompt，保留用户原意。
4. 跑 `generate` 或 `edit`。
5. 产物默认落在 `output/`，用户指定路径时用 `--out`。
6. 视觉质量重要时，生成后**亲自看一眼图**。
7. 汇报保存路径，并说明用的是哪个 provider。
8. 不要覆盖已存在的文件，除非用户明确要求替换。
9. 需要抠图时用 `removebg`（本地运行、无需 API），输出带 alpha 的 PNG；支持批量。

## 命令与参数

```bash
python scripts/cli.py list                      # 列出厂商 + 模型 + 配置状态
python scripts/cli.py doctor                    # 配置体检
python scripts/cli.py configure --provider <名> [--base-url <url>] [--api-key <k>] [--update-key] [--clear]
python scripts/cli.py generate "<prompt>" --provider <名> [--model] [--size] [--out] [--removebg] [--removebg-model u2netp] [--dry-run]
python scripts/cli.py edit "<图>" "<prompt>" --provider <名> [--mask <蒙版>] [--out] [--dry-run]
python scripts/cli.py removebg <图片> [--model u2netp] [--out] [--force]   # AI 抠图
```

各厂商默认 model / size：

| provider | 默认 model | 默认 size |
|---|---|---|
| stepfun | `step-image-edit-2` | `1024x1024` |
| seedream（已禁用） | `doubao-seedream-5-0-pro-260628` | `2K` |
| openai | `gpt-image-1` | `1024x1024` |

StepFun 独有：`--steps`（默认 8）/`--seed` /`--cfg-scale`（默认 1.0）/`--neg-prompt` /`--text-mode`。
Seedream 独有：`--size 2K|1K`，以及下方完整参数表。

## Seedream 专属参数（5.0 pro）—— ★ 已禁用，以下仅供留档

| 参数 | 说明 |
|---|---|
| `--image <路径或URL>` | 参考图，可多次。本地文件自动转 base64；用于图生图 / 多图生图（最多 10 张）。 |
| `--output-format png\|jpeg` | 输出格式，默认 jpeg。 |
| `--optimize-mode standard\|fast` | 提示词自动优化模式。 |
| `--background transparent\|opaque` | 背景透明 / 不透明（仅图生图场景、5.0 pro）。**transparent 时若参考图不透明，会自动用 rembg 转透明后再调用 API**，实现「同角色 + 原生透明」一条龙。 |
| `--layer-decomposition` | 图层拆分：返回底图 + 多个图层（仅 5.0 pro）。 |

多图结果（图层拆分 / 多图生图）会**全部落盘**到 `output/`（或 `--out` 指定前缀），主图路径返回、其余打印在下方。

## Seedream 图生图最佳实践（来自实战）—— ★ 已禁用，以下仅供留档

**单图参考 + 简洁中文 prompt 效果最佳。**

- 做「真人照片 + 中文大字封面/缩略图」时，用**一张**参考图（即真人照片），prompt 用简短直接的中文描述要加的文字和排版。
- 不要同时传「实拍底图 + 另一张风格参考图」：双图参考会把 seedream 的注意力拉扯开，导致人脸糊掉、文字排版跑偏。
- prompt 不要堆砌 200 字约束：长 prompt 会让 seedream 抓不住重点，常见表现是中文字被吞/缩水（例如"24小时"变成"24时"）。
- 如果追求清晰中文大字，优先用单图 + 极简 prompt；需要风格一致性时，靠 prompt 里的颜色和版式关键词控制，而不是再塞一张风格图。
- 2K 出图时，用 `--response-format url` 避免 `b64_json` 大响应被网络截断（`IncompleteRead` / SSL EOF）。
- **电脑端无水印，手机端水印是预览器行为**：`watermark:false` 已默认生效，本地 PNG 本身不含任何水印。用户若在手机端同步/预览时看到水印，是**手机 App / 预览器自行叠加**，与 skill 参数无关，无需重跑、无需 PIL 处理。
- **Prompt 硬约束只防模型自绘文字**：若画面中出现"AI生成"等字样（极少见，尤其中文海报），才是模型把字当内容画进去，此时才需在 prompt 末尾加：  
  > 画面中绝对不要出现任何水印、AI生成字样、平台标识、logo、签名或二维码占位。
  出图后若仍有残留字样，优先**重跑加约束**，而不是事后用 PIL 涂抹（涂抹会破坏背景纹理）。

## 通用参数

- `--force`：允许覆盖已存在的输出文件（默认保护，不覆盖）。
- `--dry-run`：只打印请求体，不调用 API（含 Seedream 专属参数）。

```bash
# Seedream 图生图（参考图）+ 图层拆分
python scripts/cli.py generate "把这张草图做成精致插画" --provider seedream \
  --image sketch.png --layer-decomposition --output-format png

# Seedream 文生图 + 透明背景 + 提示词优化
python scripts/cli.py generate "一只透明背景的赛博猫" --provider seedream \
  --background transparent --optimize-mode fast

# Seedream 原生透明生图（参考图角色保持 + 自动透明化 + 原生透明输出）
# 适用场景：多角度统一角色、需要透明 PNG 直接叠到 UI 上
python scripts/cli.py generate "Same character, repose to left side view" --provider seedream \
  --image front_character.png --background transparent --output-format png --out left.png
```

## 接新厂商：两条路

**路线 A（推荐，零代码）**：厂商若是 OpenAI 兼容的，直接用 `openai` provider
填 base-url 即可。各家 base-url / 模型名见 `references/vendors.md`，
已收录阿里云百炼、智谱 GLM、硅基流动等，并标注了来源可信度。

**路线 B（写 provider）**：接口不兼容时，在 `scripts/providers/` 下新建 py 文件，
继承 `BaseProvider`，设好 `name` / `models` / `default_model`，实现 `generate` / `edit`。
**registry 会自动扫描发现，不用改任何注册代码。**

> 写厂商信息前先查证 base-url、模型名、鉴权头三件事，没查证的不要写进速查表。

## 目录结构

```
imgbox-skill/
├── SKILL.md
├── config/
│   └── providers/
│       ├── stepfun.example.json     # 占位符模板（进 git，供参考）
│       ├── seedream.example.json    # 占位符模板（进 git，供参考）
│       ├── openai.example.json      # 占位符模板（进 git，供参考）
│       ├── stepfun.json             # ← 你的 Key（不进 git，configure 生成）
│       ├── seedream.json            # ← 你的 Key（不进 git，configure 生成）
│       └── openai.json             # ← base-url + Key（不进 git，configure 生成）
├── scripts/
│   ├── cli.py               # 统一入口：list / doctor / configure / generate / edit / removebg / poster
│   ├── config_store.py      # 配置读写 + 占位符检测
│   └── providers/
│       ├── base.py          # 抽象基类
│       ├── stepfun.py
│       ├── seedream.py
│       └── openai.py        # 通用 OpenAI 兼容（接任意厂商）
├── models/                  # 本地 AI 模型（不入 git）
│   └── u2netp/
│       └── u2netp.onnx     # U²-Net 轻量抠图模型（4.5MB）
├── references/
│   ├── vendors.md           # ← 各大生图厂商 base-url / 模型速查
│   ├── stepfun.md
│   └── seedream.md
└── output/                  # 图片默认落盘
```

## 安全

- Key 只存在 skill 内 `config/providers/*.json` 或环境变量，绝不进仓库、不写进日志。
- 配置完成后不要把 Key 回显给用户。
- Seedream 返回的是 24h 过期的签名 URL，别当永久外链用。
