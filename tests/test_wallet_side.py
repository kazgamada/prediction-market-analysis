from decimal import Decimal

from copytrader.indexer.decoder import DecodedTrade
from copytrader.monitor.detector import WatchlistDetector


def make_trade(*, maker: str, taker: str, maker_asset_id: str) -> DecodedTrade:
    return DecodedTrade(
        tx_hash="0x" + "ab" * 32,
        log_index=0,
        block_number=1,
        block_timestamp=None,
        exchange="ctf",
        order_hash="0x" + "cd" * 32,
        maker=maker,
        taker=taker,
        maker_asset_id=maker_asset_id,
        taker_asset_id="123",
        maker_amount=1000,
        taker_amount=2000,
        fee=0,
        token_id="123" if maker_asset_id == "0" else "456",
        side="BUY",
        price=Decimal("0.5"),
        size=Decimal("100"),
        notional_usd=Decimal("50"),
    )


def test_wallet_side_maker_provides_usdc_maker_buys():
    t = make_trade(maker="0xa", taker="0xb", maker_asset_id="0")
    assert WatchlistDetector.wallet_side(t, "0xa") == "BUY"
    assert WatchlistDetector.wallet_side(t, "0xb") == "SELL"


def test_wallet_side_maker_provides_tokens_maker_sells():
    t = make_trade(maker="0xa", taker="0xb", maker_asset_id="999")
    assert WatchlistDetector.wallet_side(t, "0xa") == "SELL"
    assert WatchlistDetector.wallet_side(t, "0xb") == "BUY"
