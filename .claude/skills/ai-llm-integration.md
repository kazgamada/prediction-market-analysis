---
name: ai-llm-integration
description: >-
  Claude API / Anthropic SDK を Next.js（App Router）・Server Actions・Route Handlers
  で 統合するための汎用パターン集。セットアップ・ストリーミング・バックグラウンド生成・
  マルチプロバイダー対応・プロンプト設計・エラーハンドリング・コスト管理を網羅する。
category: ai-llm
version: 3
sourceSkillIds:
  - 4119be00
  - acad8888
  - 5b9df56e
  - b844a094
  - 56cb7e84
  - d4c30a79
  - c12cc421
  - f9f3f13b
  - f3fd7006
  - 50e467ba
  - e62d03ca
  - 0ad01970
  - 150f406c
  - c4ce7df6
  - 5070feb9
generatedAt: '2026-05-23'
---

# AI / LLM Integration — Claude API & Anthropic SDK

Next.js（App Router）で Claude API を統合する際の決定版パターン集。  
セットアップから本番運用まで一貫して参照できるように設計されている。

---

## 1. セットアップ

### 依存関係

```bash
npm install @anthropic-ai/sdk
# Vercel AI SDK（ストリーミング・マルチプロバイダー対応）
npm install ai
# 環境変数バリデーション（推奨）
npm install zod
```

### 環境変数

```bash
# .env.local
ANTHROPIC_API_KEY=sk-ant-...

# マルチプロバイダー時
OPENAI_API_KEY=sk-...
GOOGLE_GENERATIVE_AI_API_KEY=...
```

### シングルトンクライアント（`lib/ai/client.ts`）

```typescript
import Anthropic from "@anthropic-ai/sdk";

if (!process.env.ANTHROPIC_API_KEY) {
  throw new Error("ANTHROPIC_API_KEY is not set");
}

// モジュールスコープでシングルトン化（cold start 対策）
export const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

// デフォルトモデル定数（一元管理）
export const DEFAULT_MODEL = "claude-opus-4-5" as const;
export const FAST_MODEL    = "claude-haiku-3-5" as const;
```

---

## 2. 基本的なメッセージ生成

### 非ストリーミング（Server Action / Route Handler 共通）

```typescript
// lib/ai/generate.ts
import { anthropic, DEFAULT_MODEL } from "./client";

export async function generateText(
  prompt: string,
  opts: {
    systemPrompt?: string;
    maxTokens?: number;
    temperature?: number;
  } = {}
): Promise<string> {
  const { systemPrompt, maxTokens = 1024, temperature = 0.7 } = opts;

  const response = await anthropic.messages.create({
    model: DEFAULT_MODEL,
    max_tokens: maxTokens,
    ...(temperature !== undefined && {
      // temperature は extended thinking 使用時は省略
    }),
    ...(systemPrompt && {
      system: systemPrompt,
    }),
    messages: [{ role: "user", content: prompt }],
  });

  const block = response.content[0];
  if (block.type !== "text") throw new Error("Unexpected response type");
  return block.text;
}
```

---

## 3. ストリーミング

### Route Handler（`app/api/chat/route.ts`）

```typescript
import { anthropic } from "@/lib/ai/client";
import { AnthropicStream, StreamingTextResponse } from "ai";

export const runtime = "edge"; // Edge Runtime 推奨

export async function POST(req: Request) {
  const { messages } = await req.json();

  const response = await anthropic.messages.create({
    model: "claude-opus-4-5",
    max_tokens: 1024,
    stream: true,
    messages,
  });

  const stream = AnthropicStream(response);
  return new StreamingTextResponse(stream);
}
```

### Server Action でストリーミング（`createStreamableValue` パターン）

```typescript
"use server";
import { createStreamableValue } from "ai/rsc";
import { anthropic } from "@/lib/ai/client";

export async function streamGenerate(prompt: string) {
  const stream = createStreamableValue("");

  (async () => {
    const response = await anthropic.messages.create({
      model: "claude-opus-4-5",
      max_tokens: 1024,
      stream: true,
      messages: [{ role: "user", content: prompt }],
    });

    for await (const chunk of response) {
      if (
        chunk.type === "content_block_delta" &&
        chunk.delta.type === "text_delta"
      ) {
        stream.update(chunk.delta.text);
      }
    }
    stream.done();
  })();

  return { output: stream.value };
}
```

### クライアント側での消費

```typescript
"use client";
import { readStreamableValue } from "ai/rsc";

export function ChatComponent() {
  const [output, setOutput] = useState("");

  const handleSubmit = async (prompt: string) => {
    const { output } = await streamGenerate(prompt);
    for await (const chunk of readStreamableValue(output)) {
      setOutput((prev) => prev + (chunk ?? ""));
    }
  };
  // ...
}
```

---

## 4. バックグラウンド生成パイプライン

AI 生成はレイテンシが高いため、**fire-and-forget + DB ステータス管理**が基本パターン。

### ステータス遷移

```
pending → generating → json_saved → html_built → published
                    ↘ error（any step）
```

### 実装パターン

```typescript
// Server Action: 即座にレスポンスを返し、バックグラウンドで生成
export async function startGeneration(contentId: string) {
  // 1. pending レコードを作成（即座にレスポンス）
  await db.contentGenerations.update({
    where: { id: contentId },
    data: { status: "generating", startedAt: new Date() },
  });

  // 2. fire-and-forget（await しない）
  runBackgroundGeneration(contentId).catch((err) => {
    console.error("Background generation failed:", err);
  });

  return { started: true };
}

async function runBackgroundGeneration(contentId: string) {
  try {
    // 3. AI 生成
    const result = await generateSingleContent(contentId);

    // 4. JSON 保存
    await db.contentGenerations.update({
      where: { id: contentId },
      data: { status: "json_saved", generatedJson: result },
    });

    // 5. HTML ビルド
    await buildHtmlFromJson(contentId);

    await db.contentGenerations.update({
      where: { id: contentId },
      data: { status: "published", completedAt: new Date() },
    });
  } catch (error) {
    await db.contentGenerations.update({
      where: { id: contentId },
      data: {
        status: "error",
        errorMessage: error instanceof Error ? error.message : String(error),
      },
    });
  }
}
```

### ポーリングで進捗確認

```typescript
// app/api/generation-status/[id]/route.ts
export async function GET(
  _req: Request,
  { params }: { params: { id: string } }
) {
  const record = await db.contentGenerations.findUnique({
    where: { id: params.id },
    select: { status: true, errorMessage: true, completedAt: true },
  });
  return Response.json(record
