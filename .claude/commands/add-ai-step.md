# add-ai-step

Claude API を使った AI 生成ステップをアプリに追加する。

## 使い方
`/add-ai-step <feature-name>`

例:
- `/add-ai-step text-generator` → テキスト生成機能
- `/add-ai-step intent-classifier` → ユーザー意図分類
- `/add-ai-step summarizer` → 要約機能

## 手順

### Step 1: Anthropic SDK をインストール
```bash
npm install @anthropic-ai/sdk
```

### Step 2: AI クライアントユーティリティを作成
`src/lib/ai/client.ts`:

```typescript
import Anthropic from "@anthropic-ai/sdk";

// シングルトンインスタンス（サーバーサイド専用）
let client: Anthropic | null = null;

export function getAiClient(): Anthropic {
  if (!client) {
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) throw new Error("ANTHROPIC_API_KEY が設定されていません");
    client = new Anthropic({ apiKey });
  }
  return client;
}
```

### Step 3: 機能別ヘルパーを作成
`src/lib/ai/<feature>.ts`:

```typescript
import Anthropic from "@anthropic-ai/sdk";
import { getAiClient } from "./client";

export interface GenerateTextOptions {
  userInput: string;
  systemPrompt: string;
  maxTokens?: number;
}

export async function generateText(options: GenerateTextOptions): Promise<string> {
  const client = getAiClient();
  const { userInput, systemPrompt, maxTokens = 500 } = options;

  const message = await client.messages.create({
    model: "claude-haiku-4-5-20251001", // コスト効率重視。長文・複雑推論が必要なら claude-sonnet-4-6
    max_tokens: maxTokens,
    system: systemPrompt,
    messages: [{ role: "user", content: userInput }],
  });

  const content = message.content[0];
  if (content.type !== "text") throw new Error("予期しないレスポンス形式");
  return content.text;
}

export interface ClassifyIntentOptions {
  userMessage: string;
  intents: string[];
}

export async function classifyIntent(
  options: ClassifyIntentOptions
): Promise<{ intent: string; confidence: number }> {
  const client = getAiClient();
  const { userMessage, intents } = options;

  const message = await client.messages.create({
    model: "claude-haiku-4-5-20251001",
    max_tokens: 100,
    system: `以下の意図リストからユーザーメッセージを分類してください。
意図リスト: ${intents.join(", ")}
JSON 形式で返答: { "intent": "<意図>", "confidence": <0-1の数値> }`,
    messages: [{ role: "user", content: userMessage }],
  });

  const content = message.content[0];
  if (content.type !== "text") throw new Error("予期しないレスポンス形式");

  try {
    return JSON.parse(content.text);
  } catch {
    return { intent: intents[0], confidence: 0.5 };
  }
}
```

### Step 4: Server Action または API Route に組み込む
```typescript
// Server Action の例
"use server";
import { generateText } from "@/lib/ai/<feature>";

export async function aiGenerateAction(input: string) {
  const result = await generateText({
    userInput: input,
    systemPrompt: "あなたは...",
  });
  return result;
}
```

### Step 5: 環境変数
`.env.example` に追加:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### コスト管理のポイント
- デフォルトは `claude-haiku-4-5-20251001`（最安価）
- 複雑な推論・長文生成が必要な場合のみ `claude-sonnet-4-6` を検討
- `max_tokens` を適切に制限してコストを抑える
- プロンプトキャッシュ（`cache_control`）を活用して繰り返しコストを削減
