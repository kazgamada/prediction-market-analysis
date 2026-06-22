---
name: text-selection-deep-qa
description: >-
  テキスト選択で「深堀Q&A」ポップアップを表示し、選択テキストについての追加質問をAIにSSEストリーミングで
  リアルタイム生成・表示する汎用機能スキル。TextSelectionPopupコンポーネント（React Portal）、
  全ページ共通配置、インライン深堀Q&A、SSEエンドポイント、トグル表示UX（新着を上・新着のみ展開・
  過去を閉じる）の実装パターンを含む。あらゆるNext.js/TypeScriptプロジェクトで再利用可能。
category: 機能
tags:
  - deep-qa
  - text-selection
  - sse
  - streaming
  - react-portal
  - eventsource
  - types
  - next.js
  - typescript
sourceSkillIds:
  - e2240759
generatedAt: '2026-06-22'
integrationStrategy: latest-first
latestSourceTimestamp: '2026-06-21T01:47:22Z'
adoptedFromArchive:
  - archive/skills/deep-qa-text-selection.md
---

# テキスト選択 深堀Q&A (SSEストリーミング) 実装スキル

## 概要

ユーザーがページ上のテキストを選択すると、その選択テキストを文脈として AIへ追加質問を投げ、SSE（Server-Sent Events）トークンストリーミングでリアルタイムに回答を表示するポップアップ機能。

### 主要コンポーネント構成

```
components/
  TextSelectionPopup.tsx     # メインポップアップ（React Portal）
  DeepQAInline.tsx           # インライン埋め込み用（履歴詳細など）
app/
  layout.tsx                 # 全ページ共通配置
  api/
    stream/
      chat/
        route.ts             # SSE エンドポイント
types/
  deep-qa.ts                 # 共通型定義
```

---

## 1. 型定義 (`types/deep-qa.ts`)

```typescript
export interface DeepQAItem {
  id: string;
  question: string;       // ユーザーが入力した質問
  answer: string;         // AIが生成した回答（ストリーミング中は部分文字列）
  isStreaming: boolean;   // ストリーミング中フラグ
  createdAt: Date;
}

export interface TextSelectionContext {
  selectedText: string;   // 選択されたテキスト
  pageContext?: string;   // ページ固有の追加コンテキスト（任意）
}

export interface StreamChatRequest {
  message: string;
  context?: string;       // 選択テキストなどの補助コンテキスト
  systemPrompt?: string;  // カスタムシステムプロンプト（任意）
}
```

---

## 2. SSE エンドポイント (`app/api/stream/chat/route.ts`)

```typescript
import { NextRequest } from "next/server";
import OpenAI from "openai";

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export async function POST(req: NextRequest) {
  const { message, context, systemPrompt }: StreamChatRequest =
    await req.json();

  // SSE ストリーム生成
  const stream = new ReadableStream({
    async start(controller) {
      const encode = (text: string) =>
        new TextEncoder().encode(`data: ${text}\n\n`);

      try {
        const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
          {
            role: "system",
            content:
              systemPrompt ??
              "あなたは親切なアシスタントです。簡潔かつ正確に回答してください。",
          },
        ];

        // 選択テキストをコンテキストとして追加
        if (context) {
          messages.push({
            role: "user",
            content: `以下のテキストを参照してください:\n\n${context}`,
          });
          messages.push({
            role: "assistant",
            content: "承知しました。そのテキストについて質問にお答えします。",
          });
        }

        messages.push({ role: "user", content: message });

        const completion = await openai.chat.completions.create({
          model: process.env.OPENAI_MODEL ?? "gpt-4o-mini",
          messages,
          stream: true,
        });

        for await (const chunk of completion) {
          const token = chunk.choices[0]?.delta?.content ?? "";
          if (token) {
            controller.enqueue(encode(token));
          }
        }

        controller.enqueue(encode("[DONE]"));
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Unknown error";
        controller.enqueue(encode(`[ERROR] ${message}`));
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
```

---

## 3. TextSelectionPopup コンポーネント (`components/TextSelectionPopup.tsx`)

```typescript
"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import type { DeepQAItem, TextSelectionContext } from "@/types/deep-qa";

interface PopupPosition {
  x: number;
  y: number;
}

interface TextSelectionPopupProps {
  /** ポップアップに渡す追加コンテキスト（ページ固有情報） */
  pageContext?: string;
  /** システムプロンプトのカスタマイズ */
  systemPrompt?: string;
  /** 機能を無効化するフラグ */
  disabled?: boolean;
}

export function TextSelectionPopup({
  pageContext,
  systemPrompt,
  disabled = false,
}: TextSelectionPopupProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [position, setPosition] = useState<PopupPosition>({ x: 0, y: 0 });
  const [selectedText, setSelectedText] = useState("");
  const [question, setQuestion] = useState("");
  const [qaItems, setQaItems] = useState<DeepQAItem[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [mounted, setMounted] = useState(false);
  const popupRef = useRef<HTMLDivElement>(null);

  // Portal マウント確認（SSR 対策）
  useEffect(() => {
    setMounted(true);
  }, []);

  // テキスト選択イベント
  const handleMouseUp = useCallback(() => {
    if (disabled) return;

    const selection = window.getSelection();
    const text = selection?.toString().trim() ?? "";

    if (text.length < 5) {
      // 短すぎる選択は無視
      return;
    }

    const range = selection?.getRangeAt(0);
    const rect = range?.getBoundingClientRect();
    if (!rect) return;

    setSelectedText(text);
    setPosition({
      x: rect.left + rect.width / 2 + window.scrollX,
      y: rect.top + window.scrollY - 8, // 選択範囲の直上
    });
    set
