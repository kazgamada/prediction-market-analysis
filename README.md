# polymarket-copytrader

Polymarket の高勝率ウォレットを発見し、その約定を遅延付きで模倣するコピートレードボット。

## ステータス

**Phase 0 — 戦略の edge 検証**

過去 90 日の OrderFilled イベントを inde​x し、上位ウォレットを 30〜60 秒遅延で模倣した場合に
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

## 開発

```sh
uv sync --all-extras
cp .env.example .env  # 値を埋める
pytest
```

## 履歴

このリポジトリは元々 `prediction-market-analysis`（Polymarket / Kalshi の
オフラインアナリシス集）として存在していた。git 履歴に残っているため、
indexer / backtest コードは必要に応じてそこから移植する。

## License

MIT
