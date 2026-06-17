---
description: 複数ツールリポに同一の実装指示を Issue 経由で一斉投下する
---

# /apply-to-tools

`skills/multi-tool-bulk-apply/SKILL.md` のフローを起動する。

## 使い方

```
/apply-to-tools <repo>... [--parallel N] [--dry-run] [--no-direct-push] -- <prompt>
```

### 引数

- `<repo>...`: `owner/repo` 形式の空白区切り。1個以上
- `--parallel N`: 同時起動セッション数（省略時 3）
- `--dry-run`: Issue は作らず、起動内容のみ表示
- `--no-direct-push`: main 直接 push を許可しない（feature ブランチ + PR を要求）
- `-- <prompt>`: `--` の後が実装指示本文

### 例

```
/apply-to-tools kazgamada/tool-a kazgamada/tool-b kazgamada/tool-c \
  --parallel 3 \
  -- アカウント認証と admin/user role 分離、セキュリティ対策を実装してください
```

## 実行フロー

1. 引数をパースし、`--` より前は repo / オプション、後ろは prompt として扱う
2. `skills/multi-tool-bulk-apply/SKILL.md` の禁止事項（§機密情報チェック）を確認
3. `/api/apply-to-tools` を POST し、各リポに Issue を作成
4. 結果を表形式で表示:

```
| repo                  | status   | issue                 |
|-----------------------|----------|-----------------------|
| kazgamada/tool-a      | started  | #42 (URL)             |
| kazgamada/tool-b      | failed   | HTTP 404: not found   |
```

5. 失敗リポがあれば `--retry-failed <group-id>` を案内
