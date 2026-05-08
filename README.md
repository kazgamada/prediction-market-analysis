# polymarket-copytrader

Polymarket の高勝率ウォレットを発見し、その約定を遅延付きで模倣するコピートレードボット。

CLI + Streamlit 管理 UI 同梱。Phase 0（オフラインの edge 検証）から Phase 4（微小ライブ）まで一貫したワークフローで進められる。

## ステータス

**Phase 0 — 戦略の edge 検証**

過去 90 日の OrderFilled イベントを index し、上位ウォレットを 30〜60 秒遅延で模倣した場合に
プラス期待値が残るかをバックテストで確認する段階。ここで edge が確認できなければ撤退する。

## ロードマップ

| Phase | 内容 | 期間 | 資金 |
|---|---|---|---|
| 0 | Replay backtest で edge 検証 | 1〜2 週 | $0 |
| 1 | ウォレットランキング MVP | 1〜2 週 | $0 |
| 2 | ライブ監視（read-only） | 1 週 | $0〜$5 |
| 3 | ペーパートレード | 2 週 | $0 |
| 4 | 微小ライブ（上限 $50） | 2 週 | $50〜$100 |
| 5 | 段階的スケール | — | $300+ |

各フェーズで明示した成功条件をクリアしないと次に進まない。

## アーキテクチャ

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Polygon RPC │ ←── │   indexer    │ ──→ │  Postgres    │
│  (HTTP/WS)   │     │ (backfill +  │     │  (trade,     │
│              │     │   stream)    │     │   wallet,    │
└──────────────┘     └──────────────┘     │   signal,    │
                                          │   order, …)  │
┌──────────────┐     ┌──────────────┐     │              │
│  Polymarket  │ ←── │   executor   │ ←── │              │
│  CLOB API    │     │ (paper/live) │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
                            ↑                    ↑
                            │                    │
                     ┌──────┴──────┐      ┌──────┴──────┐
                     │   monitor   │      │   web UI    │
                     │ (watchlist  │      │ (Streamlit) │
                     │  detector)  │      │             │
                     └─────────────┘      └─────────────┘
```

## クイックスタート（ローカル）

```sh
# 1. 依存をインストール
uv sync --extra dev

# 2. .env を作成
cp .env.example .env
# 必須: POLYGON_RPC_HTTP, POLYGON_RPC_WS（Alchemy / QuickNode 等の URL）
# Phase 4 で必要: POLYMARKET_API_*, WALLET_PRIVATE_KEY

# 3. Postgres を起動 + マイグレーション
docker compose up -d postgres
alembic upgrade head

# 4. 過去データを取得（数時間）
copytrader backfill
copytrader sync-markets

# 5. Phase 0: ランキング + リプレイ
copytrader rank --window 30 --watchlist-top 10
copytrader replay --window 30 --delays 30,60,120
```

### 管理 UI（Streamlit）

```sh
streamlit run src/copytrader/web/app.py
# → http://localhost:8501
```

UI からできる操作：
- **Status**: 最新の signal / position / order / risk_event を表示
- **Watchlist**: ウォレットアドレスを入力して追加・削除
- **Rank**: window / 最低取引数 / 最低 volume を入力 → ランキング実行 → 上位 N を watchlist 化
- **Replay**: delay / コピーサイズ / slippage を入力 → wallet を選択して replay
- **Inspect**: 任意のアドレスを入力 → トークン別 PnL を表示
- **Actions**: backfill / sync-markets / reconcile / poll をボタン一発で

`WEB_PASSWORD` を環境変数で設定すると簡易パスワードゲートが有効になる。

## CLI コマンド

```sh
# データ取得
copytrader backfill [--from-block N] [--to-block M] [--chunk-size 1000]
copytrader sync-markets

# 分析
copytrader rank --window 30 --min-trades 30 --min-volume 5000 --watchlist-top 10
copytrader replay --window 30 --delays 30,60,120 --copy-usd 50
copytrader inspect <address> --window 30

# Watchlist
copytrader watch add <address> [--note "memo"]
copytrader watch list
copytrader watch remove <address>

# 監視 / 取引
copytrader monitor                                   # read-only WS subscription
copytrader paper --copy-usd 5                        # ペーパートレード
copytrader live  --copy-usd 5 --i-understand-the-risk  # 実発注（caps 厳しめ）

# 運用
copytrader status                                    # 直近の signal / position / risk
copytrader reconcile [--no-trip]                     # オンチェーン残高と DB の照合
copytrader poll                                      # CLOB の order status を反映
copytrader balance                                   # 自ウォレットの USDC / アローワンス
```

## Fly.io デプロイ

事前に [flyctl](https://fly.io/docs/hands-on/install-flyctl/) をインストールし `fly auth login` 済みであること。

```sh
# .env に POLYGON_RPC_HTTP / POLYGON_RPC_WS を入れた状態で：
./scripts/deploy-fly.sh
```

スクリプトがやること:
1. `fly apps create polymarket-copytrader`
2. `fly pg create polymarket-copytrader-db` + `fly pg attach`
3. `fly secrets set` で env を全部送り込む（.env から読み取り）
4. `fly deploy` — `web`（Streamlit）と `monitor`（WS subscriber）を同時起動

完了後:
- `fly logs` でログ
- `fly open` で UI を開く
- `fly ssh console -C 'copytrader rank --watchlist-top 10'` のように任意の CLI を実行
- `paper` / `live` を起動するときは `fly.toml` の processes セクションでコメントを外して `fly deploy`

## リスク制御

Live モードは下記が **すべて** 入っている：

| 制御 | デフォルト |
|---|---|
| `max_order_usd` | $5 |
| `max_position_usd_per_token` | $20 |
| `max_total_exposure_usd` | $50 |
| `max_daily_loss_usd` | $20 |
| `max_concurrent_orders` | 5 |
| 起動ガード | `--i-understand-the-risk` フラグ必須 |
| Killswitch | 日次損失到達 / オンチェーン残高乖離 / 連続発注エラー |
| Reconciler | 5 分おきに CTF 残高と DB の position を突合 |
| Order poller | 30 秒おきに CLOB の order status を実値に更新 |

## 履歴

このリポジトリは元々 `prediction-market-analysis`（Polymarket / Kalshi のオフラインアナリシス集）として存在していた。git 履歴に残っているため、必要があれば旧 indexer / 分析コードは `git show 0accd98:src/...` で取り出せる。

## License

MIT
