# polymarket-copytrader

Polymarket の高勝率ウォレットを発見し、その約定を遅延付きで模倣するコピートレードボット。
Phase 0 — オフラインの edge 検証 — に絞った再構築版。

過去の実装で繰り返し発生した 22 件のトラブル（`docs/requirements/REBUILD.md` §1.2）を構造的に潰した上で、**ブラウザだけで運用できる** ことを設計目標にしている。

## 設計

- **3 プロセス分離**: `web` (Streamlit) / `indexer` (Polygon RPC backfill + WS) / `worker` (job queue)
- **状態は Postgres に一元化**: cursors / jobs / job_logs / rpc_dead_letters / settings
- **失敗の粒度を分ける**: RPC chunk 単位の失敗は dead-letter に逃がし、プロセス全体は止めない
- **長時間ジョブは worker 側**: Streamlit にはボタン 1 つでジョブを enqueue させるだけ

詳細は:
- `docs/requirements/REBUILD.md` — 要件定義
- `docs/plans/IMPLEMENTATION_PLAN.md` — 実装計画
- `docs/ops/{deploy,troubleshoot,disaster-recovery}.md` — 運用手順

## ローカル開発

```sh
# 依存と venv
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 3 プロセスを compose で起動
cp .env.example .env  # POLYGON_RPC_HTTP / WS / WEB_PASSWORD を埋める
docker compose up -d

# UI
open http://localhost:8501       # Streamlit
curl http://localhost:8080/readyz  # health
```

3 プロセスのログを個別に見るには `docker compose logs -f web|indexer|worker`。

## Phase 0 を 1 回まわす

UI で:
1. ブラウザで `http://localhost:8501` を開く
2. `WEB_PASSWORD` を入力
3. サイドバーから `Phase0` ページ → 「Run Phase 0」
4. `Jobs` ページで進捗を見る（live log が 2 秒間隔で流れる）
5. 終了したら同ページで result JSON を確認

## 本番デプロイ（Fly.io）

`docs/ops/deploy.md` 参照。main へ push すれば GitHub Actions が `flyctl deploy` を走らせる。

## テスト

```sh
# Postgres を立ち上げてから
DATABASE_URL=postgresql+psycopg://copytrader:copytrader@localhost:5432/copytrader_test \
  alembic upgrade head
DATABASE_URL=postgresql+psycopg://copytrader:copytrader@localhost:5432/copytrader_test \
  pytest -q
```

unit のみなら `pytest tests/unit -q` で OK（DB 不要）。

## 撤退判定（Phase 0）

`docs/requirements/REBUILD.md` §12 Q1 で事前に決めた数値基準を満たさなければ撤退。Phase 1 以降には進まない。

## License

MIT
