# 公文正文稿排版规范

MyCowork 交付 `.docx` 时**默认按本规范**排版（机关常用正文稿 / 送审稿）。套红正式发文仍见 [gb-t-9704-2012-standard.md](./gb-t-9704-2012-standard.md)。

字号对照：二号 = 22pt，三号 = 16pt，小四 = 12pt。

## 文面结构

```
标题                    ← 方正小标宋_GBK · 二号 · 居中
<空一行>
2026年8月16日            ← 方正楷体_GBK · 三号 · 居中
讨论稿                   ← 可选；政策意见类标注，同上字体字号居中
<空一行>
[主送机关]：              ← 有主送时顶格，后接冒号
一、一级标题              ← 方正黑体_GBK · 三号
（一）二级标题            ← 方正楷体_GBK · 三号
1. 三级标题              ← 方正仿宋_GBK · 三号 · 加粗
正文段落……               ← 方正仿宋_GBK · 三号 · 首行缩进二字
```

- 标题与日期之间空一行；日期（及可选标注）与正文之间再空一行。
- 这两处空行是规范要求的结构间距，须保留（固定行距 29 磅的空段），不要改成 `spaceBefore` / `spaceAfter`。
- 成文日期用阿拉伯数字全称，月日不编虚位：`2026年8月16日`，不用 `08月16日`。
- 政策意见、方案、讨论类文稿，日期下一行居中标注稿次（如「讨论稿」「征求意见稿」）。

## 字体与字号

优先使用方正 GBK 字体。本机没有时按右列回退，**同一篇不要混用多种回退**。

| 要素 | 字体 | 字号 | 对齐 / 样式 | 回退 |
|------|------|------|-------------|------|
| 标题 | 方正小标宋_GBK | 二号 22pt | 居中 | 华文中宋 / 宋体 |
| 日期、稿次标注 | 方正楷体_GBK | 三号 16pt | 居中 | 楷体 / KaiTi |
| 正文一级标题（一、） | 方正黑体_GBK | 三号 16pt | 首行缩进二字 | 黑体 / SimHei |
| 正文二级标题（（一）） | 方正楷体_GBK | 三号 16pt | 首行缩进二字 | 楷体 / KaiTi |
| 正文三级标题（1.） | 方正仿宋_GBK | 三号 16pt | 加粗；首行缩进二字 | 仿宋 / FangSong |
| 正文内容 | 方正仿宋_GBK | 三号 16pt | 首行缩进二字 | 仿宋 / FangSong |
| 全文数字、西文 | Times New Roman | 三号 16pt | 随所在段落 | — |
| 页码 | 宋体 | 小四 12pt | 页脚居中 | SimSun |

层次序数仍用 `一、` / `（一）` / `1.` / `（1）`。第四层与正文同字体、不加粗。

中西文混排：东亚字体走 `font.ea`，数字与西文走 `font.latin=Times New Roman`。

## 页面与行距

| 项目 | 取值 |
|------|------|
| 纸张 | A4（210mm × 297mm） |
| 上 / 下页边距 | 3 cm |
| 左 / 右页边距 | 2.9 cm |
| 页眉距边界 | 1.5 cm |
| 页脚距边界 | 1.75 cm |
| 全文行距 | **固定值 29 磅**（`lineSpacing=29pt`，`lineRule=exact`） |
| 段前段后 | 0（行距已固定，不要再加段间距） |

## 页码

- 位置：页脚居中。
- 样式：长线段类型，页码两侧加长横线，如 `—— 1 ——`（用 PAGE 域，不要写死数字）。
- 字体：宋体小四。

## 与 officecli-docx 通用规则的差异

生成公文 `.docx` 时以**本文件为准**，不要套用 officecli-docx 的报告默认值：

- 不要用 Calibri / 11pt / 1.15 倍行距。
- 不要为「3 个以上标题」自动加 TOC。
- 不要做封面填充率、Smart quotes 等商务报告要求。
- 标题与日期之间的空行必须保留。

## officecli 要点

属性名以 `officecli help docx section` / `officecli help docx paragraph` 为准。

写完 `.docx` 后必须运行（或调用工具 `docx_gongwen_format`）：

系统在「公文写作助手」任务结束时会再次套用本规范，覆盖误用的 GB/T 9704 页面（3.7cm / 2.8cm / 28磅 / 仿宋_GB2312）。

```bash
FILE="公文.docx"
officecli create "$FILE"
officecli open "$FILE"

officecli set "$FILE" / \
  --prop pageWidth=21cm --prop pageHeight=29.7cm \
  --prop marginTop=3cm --prop marginBottom=3cm \
  --prop marginLeft=2.9cm --prop marginRight=2.9cm \
  --prop marginHeader=1.5cm --prop marginFooter=1.75cm

# 标题
officecli add "$FILE" /body --type paragraph \
  --prop text="××关于××的请示" --prop align=center \
  --prop size=22pt --prop lineSpacing=29pt --prop lineRule=exact \
  --prop spaceBefore=0pt --prop spaceAfter=0pt \
  --prop font.ea="方正小标宋_GBK" --prop font.latin="Times New Roman"

# 空一行
officecli add "$FILE" /body --type paragraph \
  --prop text="" --prop size=16pt --prop lineSpacing=29pt --prop lineRule=exact

# 日期
officecli add "$FILE" /body --type paragraph \
  --prop text="2026年8月16日" --prop align=center \
  --prop size=16pt --prop lineSpacing=29pt --prop lineRule=exact \
  --prop spaceBefore=0pt --prop spaceAfter=0pt \
  --prop font.ea="方正楷体_GBK" --prop font.latin="Times New Roman"

# 空一行后再写主送 / 正文
officecli add "$FILE" /body --type paragraph \
  --prop text="" --prop size=16pt --prop lineSpacing=29pt --prop lineRule=exact

# 正文（首行缩进二字：200 = 2 字符）
officecli add "$FILE" /body --type paragraph \
  --prop text="根据……现将有关事项通知如下：" \
  --prop size=16pt --prop lineSpacing=29pt --prop lineRule=exact \
  --prop spaceBefore=0pt --prop spaceAfter=0pt \
  --prop font.ea="方正仿宋_GBK" --prop font.latin="Times New Roman"
officecli set "$FILE" "/body/p[last()]" --prop firstLineChars=200

# 一级标题：黑体；二级：楷体；三级：仿宋加粗。均三号、固定 29 磅。

# 页脚长线段页码
officecli add "$FILE" / --type footer --prop type=default \
  --prop size=12pt --prop font.ea="宋体" --prop font.latin="Times New Roman" \
  --prop text="—— " --prop field=page
officecli add "$FILE" "/footer[1]/p[1]" --type run --prop text=" ——"
officecli set "$FILE" "/footer[1]/p[1]" --prop align=center

officecli close "$FILE"
officecli validate "$FILE"
```

一级 / 二级标题不要加粗（字体本身已区分）；仅三级标题 `bold=true`。
