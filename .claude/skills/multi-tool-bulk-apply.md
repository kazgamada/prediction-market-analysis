---
name: multi-tool-bulk-apply
description: >-
  複数のツールリポジトリ（kazgamada/*）に対して同一の実装指示を一斉に伝達する。
  各リポに Claude Code on the web を起動するトリガー Issue を作成し、
  Issue 経由で並列にエージェントを動かす。
  「すべてのツールに認証を入れて」「全リポに XX を実装」のような横断作業で使う。
category: orchestration
version: 1
changedAt: '2026-05-11T00:00:00.000Z'
---

# Multi-Tool Bulk Apply

複数のツールリポに **同一の実装指示** を Issue 経由で一斉投下する Skill。

## いつ使うか

- 「すべてのツールに認証を入れて」「全リポにセキュリティ対策を実装」のような **横断的な実装指示**
- 共通 Skill のマスター更新後、全ツールへの再適用
- 単一ツールで完結する場合は使わない（普通に Claude Code で実装すればよい）

## 利用フロー（必須）

1. **対象リポと指示の確認**
   - 対象リポは `kazgamada/owner/repo` 形式の空白区切り
   - 機密情報を含む指示は拒否する（§6 共通ルール）
2. **既存知見の確認**
   - 指示内容に該当する `skills/` Skill を `grep` で確認し、各 Issue 本文に参照を含める
3. **Issue 一斉作成**
   - `/api/apply-to-tools` を POST する。ブラウザから使う場合は `/multi-tool-bulk-apply` ページを開く
   - body: `{ repos, prompt, parallel, dryRun, allowDirectPush }`
4. **結果の集約**
   - 各リポの Issue URL と起動ステータスをユーザーに返す
   - 失敗リポは原因（HTTP ステータス・本文）を併記

## 禁止事項

- 機密情報（API キー・顧客名等）を `prompt` に含めないこと。Issue 本文として GitHub に永続化される
- `allowDirectPush: false` のまま実行しない（§0.2 蟻地獄回避ルール）と判断する場合は理由を明示
- 同一 group-id の再実行は失敗リポだけに絞ること（成功リポへの重複 Issue を避ける）

## インターフェース

### Web UI

`/multi-tool-bulk-apply` ページ。

### API

```
POST /api/apply-to-tools
Content-Type: application/json

{
  "repos": ["kazgamada/tool-a", "kazgamada/tool-b"],
  "prompt": "アカウント認証と admin role 分離を実装してください",
  "parallel": 3,
  "dryRun": false,
  "allowDirectPush": true
}
```

レスポンス:

```json
{
  "groupId": "b7c4-2026-05-11-1438",
  "results": [
    { "repo": "kazgamada/tool-a", "status": "started", "issueUrl": "...", "issueNumber": 42 },
    { "repo": "kazgamada/tool-b", "status": "failed", "error": "HTTP 404: ..." }
  ]
}
```

### スラッシュコマンド

`.claude/commands/apply-to-tools.md` を参照。

## 環境変数

- `GITHUB_TOKEN` または `GH_PAT`: Issue 作成権限（`issues: write`）が必要
- 対象リポは Claude GitHub App がインストールされていること（Issue の `@claude` メンションでトリガー）

## アーキテクチャ

```
[UI / Skill] ─POST─▶ /api/apply-to-tools
                          │
                          ▼ Promise.all (parallel chunk)
                  GitHub REST /repos/{owner}/{repo}/issues
                          │
                          ▼ @claude メンション
                  Claude Code on the web セッション起動
```

## 関連

- `docs/requirements/multi-tool-bulk-apply.md` — 要件定義書
- `docs/mockups/multi-tool-bulk-apply.html` — UI モック
- `app/multi-tool-bulk-apply/page.tsx` — Web UI
- `app/api/apply-to-tools/route.ts` — API 実装
