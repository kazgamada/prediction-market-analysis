---
category: コンテンツ
sourceSkillIds:
  - e301cd65
  - c9088125
  - 2c100c6b
  - 8858b341
  - efef9795
  - dcb55994
  - 8f0a931f
  - d76b5267
  - 2e7aae43
  - 99551a8a
  - 5bea7d75
  - '18060776'
  - 698872c1
  - a054e89b
  - e62ee81d
  - 0d809ae6
  - baae9114
generatedAt: '2026-05-11'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-05-10T19:11:30+00:00'
adoptedFromArchive:
  - archive/aegis-market-os/.claude/skills/medical-lecture-slide-design.md
  - archive/ai-agent-hub/.claude/skills/medical-lecture-slide-design.md
  - archive/ai-company/.claude/skills/medical-lecture-slide-design.md
  - archive/AISaaS/.claude/skills/medical-lecture-slide-design.md
  - archive/KOKOKARA/.claude/skills/medical-lecture-slide-design.md
  - archive/LINE-AI/.claude/skills/medical-lecture-slide-design.md
  - archive/manabi-ai/.claude/skills/medical-lecture-slide-design.md
  - archive/medical-learning-ai/.claude/skills/medical-lecture-slide-design.md
  - >-
    archive/openspace-skill-manager/.claude/skills/medical-lecture-slide-design.md
  - archive/pptx-translator/.claude/skills/medical-lecture-slide-design.md
---
```yaml
---
name: medical-lecture-slide-design
description: >-
  医療専門職（理学療法士・医師・柔道整復師など）向けの講義スライドを、白背景・黒文字・メイリオで統一し、
  印刷・PDF配布に適した読みやすいレイアウトで PPTX 形式で作成・修正するスキル。
  病態理解から臨床推論、患者教育まで幅広いシーンに対応。
category: コンテンツ
---
```

# 医療資格者向け講義スライド設計

## 概要

医療専門職（理学療法士・医師・柔道整復師など）を対象に、講義スライドを **読みやすく・印刷しやすく・臨床的に正確に** 作成・修正するスキル。

- 出力形式: PPTX（PowerPoint 互換）
- 配布想定: 印刷配布・PDF 共有・プロジェクター投影
- 対象領域: 病態理解 / 解剖学 / 臨床推論 / 患者教育 / 医療倫理 など

---

## デザイン原則

### 1. 基本スタイル規約

| 要素 | 設定値 |
|------|--------|
| 背景色 | 白（`#FFFFFF`） |
| 文字色 | 黒（`#000000`）または濃いグレー（`#1A1A1A`） |
| フォント | メイリオ（日本語）/ Arial または Calibri（英数字） |
| スライドサイズ | A4 横（297×210mm）または 16:9（印刷時は A4 に変換） |
| マージン | 上下左右 最低 15mm |

> **理由**: 白黒印刷での視認性と、PDF 変換後のフォント埋め込み安定性を確保するため。カラースライドは補足的使用にとどめる。

### 2. 文字サイズ階層

```
タイトル（スライド表題）: 32〜36pt / 太字
見出し H2 相当:          24〜28pt / 太字
本文・箇条書き:           18〜22pt / 標準
注釈・出典・補足:         12〜14pt / 標準
```

> **注意**: 18pt 未満は印刷後に読めなくなるリスクがあるため原則禁止。

### 3. 1スライド 1メッセージの原則

- 1 枚のスライドで伝えるポイントは **最大 3〜5 項目**
- 箇条書きは簡潔な体言止めを推奨（「〜である」より「〜の存在」）
- 長文解説は **ノート欄** に記載し、スライド本文に含めない

---

## スライド構成パターン

### パターン A: 講義スライド（標準）

```
[スライド 1] 表紙
  - タイトル、サブタイトル、講師名、日付、所属

[スライド 2] 目次・到達目標
  - 学習目標（〜できるようになる）を 3〜5 項目

[スライド 3〜N] 本編
  - 概念説明 → 解剖・病態 → 評価・診断 → 治療・介入 → 症例

[スライド N+1] まとめ
  - キーポイントの再掲

[スライド N+2] 参考文献
  - Vancouver 方式または APA 方式で統一
```

### パターン B: 症例提示スライド

```
[症例紹介]    年齢・性別・主訴・現病歴（個人情報は匿名化）
[初期評価]    バイタル、身体所見、検査結果
[臨床推論]    鑑別診断リスト → 優先順位づけ
[介入計画]    治療方針・目標設定
[経過・考察]  変化の記録、なぜこの治療か
[学習ポイント] 聴衆へのテイクアウェイメッセージ
```

### パターン C: 患者教育スライド

```
- 専門用語を極力排除、平易な日本語
- 図解・イラストを優先（テキスト比率 < 40%）
- 「あなたにできること」アクションステップを末尾に必ず記載
```

---

## PPTX 生成・修正の実装ガイド

### python-pptx を使った基本構造（参考実装）

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ---- 定数定義 ----
FONT_NAME_JP = "メイリオ"
FONT_NAME_EN = "Arial"
COLOR_BLACK  = RGBColor(0x1A, 0x1A, 0x1A)
COLOR_WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
COLOR_ACCENT = RGBColor(0x00, 0x5B, 0xAD)  # 強調用（濃紺）

TITLE_SIZE   = Pt(34)
HEADING_SIZE = Pt(26)
BODY_SIZE    = Pt(20)
CAPTION_SIZE = Pt(13)

SLIDE_W = Inches(13.33)  # 16:9
SLIDE_H = Inches(7.5)

def create_medical_presentation() -> Presentation:
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs

def add_title_slide(prs: Presentation, title: str, subtitle: str, author: str, date: str):
    """表紙スライドを追加"""
    layout = prs.slide_layouts[0]  # Title Slide
    slide  = prs.slides.add_slide(layout)

    # タイトル
    tf = slide.shapes.title.text_frame
    tf.text = title
    _apply_font(tf.paragraphs[0], FONT_NAME_JP, TITLE_SIZE, bold=True)

    # サブタイトル（著者・日付）
    body = slide.placeholders[1].text_frame
    body.text = f"{subtitle}\n{author}　{date}"
    for para in body.paragraphs:
        _apply_font(para, FONT_NAME_JP, BODY_SIZE)

def add_content_slide(
    prs: Presentation,
    title: str,
    bullets: list[str],
    notes: str = ""
) -> None:
    """箇条書き本文スライドを追加"""
    layout = prs.slide_layouts[1]  # Title and Content
    slide  = prs.slides.add_slide(layout)

    slide.shapes.title.text = title
    _apply_font(slide.shapes
