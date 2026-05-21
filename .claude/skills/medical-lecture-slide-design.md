---
name: medical-lecture-slide-design
description: >-
  医療専門職（理学療法士・医師・柔道整復師など）向けの講義スライドを、 白背景・黒文字・メイリオで統一し、印刷・PDF配布に適した読みやすいレイアウトで
  PPTX形式で作成・修正するスキル。病態理解から臨床推論、患者教育まで幅広いシーンに対応。
  Next.js/TypeScriptプロジェクトからPPTX生成APIを呼び出す実装パターンも含む。
category: コンテンツ
tags:
  - medical
  - slide
  - pptx
  - lecture
  - presentation
  - pdf
  - typescript
  - nextjs
abstractionLevel: 2
targetStack:
  - Next.js
  - TypeScript
sourceSkillIds:
  - 8215d63c
generatedAt: '2026-05-19'
---

# Medical Lecture Slide Design Skill

## 概要

医療専門職向け講義スライドの設計・生成・修正を行うための統合スキル。
「白背景・黒文字・メイリオ」を鉄則とし、印刷・PDF配布に耐える視認性と情報密度を両立する。

---

## 1. デザイン原則（Design Principles）

### 1.1 視覚的統一ルール

| 要素 | 規定値 | 理由 |
|------|--------|------|
| 背景色 | 白（`#FFFFFF`） | 印刷コスト削減・視認性 |
| 文字色 | 黒（`#000000`）/ 濃グレー（`#1A1A1A`） | コントラスト確保 |
| 日本語フォント | メイリオ（Meiryo） | Windows環境での安定表示 |
| 英数字フォント | Arial または Calibri | メイリオとの親和性 |
| スライドサイズ | 16:9（幅33.87cm × 高19.05cm） | 標準プロジェクター対応 |
| 配布用代替 | A4縦（21cm × 29.7cm） | 印刷・PDF配布時 |

### 1.2 文字サイズ階層

```
タイトル（スライド見出し）  : 28〜32pt  Bold
サブタイトル・節見出し      : 20〜24pt  Bold
本文・箇条書き             : 16〜18pt  Regular
補足・注記・出典           : 12〜14pt  Regular / Italic
表内テキスト               : 14〜16pt
```

### 1.3 カラーアクセント（最小限使用）

```
強調1（重要概念）  : #C0392B  （深赤）
強調2（警告・注意）: #E67E22  （オレンジ）
強調3（ポジティブ）: #2980B9  （青）
区切り線・罫線     : #BDBDBD  （薄グレー）
表ヘッダー背景     : #F2F2F2  （極薄グレー）
```

> ⚠️ アクセントカラーはスライド全体の10%以下に抑える。グラデーション・影・装飾的図形は原則禁止。

---

## 2. スライド構成パターン

### 2.1 標準スライドタイプ一覧

| タイプ | 用途 | レイアウト構造 |
|--------|------|---------------|
| `title` | 講義表紙 | タイトル・サブタイトル・講師名・日付 |
| `agenda` | 目次 | 番号付きリスト、現在位置ハイライト |
| `section-break` | 章区切り | 章番号＋章タイトルのみ（シンプル） |
| `content` | 通常コンテンツ | 見出し＋箇条書き or 説明文 |
| `two-column` | 比較・対照 | 左右カラム（50/50 or 60/40） |
| `table` | データ・分類 | 表（ヘッダー薄グレー背景） |
| `figure` | 図・画像 | 画像＋キャプション（出典明記） |
| `summary` | まとめ | 重要ポイント3〜5項目 |
| `quiz` | 確認問題 | 問題文＋選択肢 or 空欄 |
| `reference` | 参考文献 | 文献リスト（小フォント） |

### 2.2 医療特化コンテンツパターン

```
病態スライド     : 病態生理の流れ図（テキストボックス＋矢印）
臨床推論スライド  : SOAP形式 or 問題リスト形式
解剖スライド     : 図＋ラベル（画像は外部提供 or 説明テキスト代替）
薬理スライド     : 作用機序・副作用を表形式
リハビリスライド  : 段階的目標設定（急性期→回復期→生活期）
患者教育スライド  : 平易な言葉・大きな文字・アイコン活用
```

---

## 3. PPTX生成の実装パターン（TypeScript）

### 3.1 依存ライブラリ

```bash
npm install pptxgenjs
# または
npm install officegen  # サーバーサイド向け
```

### 3.2 型定義

```typescript
// types/slide.ts

export type SlideType =
  | 'title'
  | 'agenda'
  | 'section-break'
  | 'content'
  | 'two-column'
  | 'table'
  | 'figure'
  | 'summary'
  | 'quiz'
  | 'reference';

export interface SlideContent {
  type: SlideType;
  title: string;
  subtitle?: string;
  body?: string | string[];
  leftColumn?: string[];
  rightColumn?: string[];
  tableData?: TableData;
  figureUrl?: string;
  figureCaption?: string;
  notes?: string; // 発表者ノート
}

export interface TableData {
  headers: string[];
  rows: string[][];
}

export interface LectureConfig {
  title: string;
  subtitle?: string;
  lecturer: string;
  date: string;          // "2026-05-11" ISO形式
  institution?: string;
  slides: SlideContent[];
}

export interface PptxGenerationResult {
  success: boolean;
  filename: string;
  slideCount: number;
  error?: string;
}
```

### 3.3 デザイン定数

```typescript
// lib/slideDesign.ts

export const SLIDE_DESIGN = {
  // フォント
  font: {
    japanese: 'メイリオ',
    latin: 'Arial',
  },

  // カラー
  color: {
    background: 'FFFFFF',
    textPrimary: '1A
