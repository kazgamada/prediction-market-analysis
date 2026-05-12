"""Unit tests for the V2 OrderFilled decoder."""

from decimal import Decimal

from copytrader.indexer.decoder import decode


def _log(block=100, tx="0x" + "ab" * 32, log_index=0):
    return {
        "blockNumber": block,
        "transactionHash": bytes.fromhex(tx[2:]),
        "logIndex": log_index,
    }


def test_decode_v2_maker_buy_means_taker_sell():
    """V2 side=0 (maker BUY): maker は USDC を出してトークンを買う。
    taker のpov ではトークンを USDC で売っている = SELL。
    """
    log = _log()
    args = {
        "orderHash": bytes.fromhex("ab" * 32),
        "maker": "0xMaker0000000000000000000000000000000000",
        "taker": "0xTaker0000000000000000000000000000000000",
        "side": 0,  # maker BUY
        "tokenId": 12345,
        "makerAmountFilled": 30_000_000,  # 30 USDC
        "takerAmountFilled": 100_000_000,  # 100 tokens
        "fee": 0,
        "builder": bytes(32),
        "metadata": bytes(32),
    }
    t = decode(log, args, "ctf")
    assert t is not None
    assert t.token_id == "12345"
    assert t.side == "SELL"
    assert t.price == Decimal("0.30000000")
    assert t.size == Decimal("100.000000")
    assert t.notional_usd == Decimal("30.000000")
    # 後方互換: maker_asset_id="0" (USDC), taker_asset_id=token_id
    assert t.maker_asset_id == "0"
    assert t.taker_asset_id == "12345"


def test_decode_v2_maker_sell_means_taker_buy():
    """V2 side=1 (maker SELL): maker はトークンを出して USDC を受け取る。
    taker のpov ではトークンを USDC で買っている = BUY。
    """
    log = _log()
    args = {
        "orderHash": bytes.fromhex("cd" * 32),
        "maker": "0xMaker0000000000000000000000000000000000",
        "taker": "0xTaker0000000000000000000000000000000000",
        "side": 1,  # maker SELL
        "tokenId": 9876,
        "makerAmountFilled": 100_000_000,  # 100 tokens
        "takerAmountFilled": 70_000_000,  # 70 USDC
        "fee": 0,
        "builder": bytes(32),
        "metadata": bytes(32),
    }
    t = decode(log, args, "negrisk")
    assert t is not None
    assert t.token_id == "9876"
    assert t.side == "BUY"
    assert t.price == Decimal("0.70000000")
    assert t.notional_usd == Decimal("70.000000")
    assert t.maker_asset_id == "9876"
    assert t.taker_asset_id == "0"


def test_decode_v2_skips_zero_token_id():
    args = {
        "orderHash": bytes.fromhex("00" * 32),
        "maker": "0x" + "1" * 40,
        "taker": "0x" + "2" * 40,
        "side": 0,
        "tokenId": 0,
        "makerAmountFilled": 1,
        "takerAmountFilled": 1,
        "fee": 0,
        "builder": bytes(32),
        "metadata": bytes(32),
    }
    assert decode(_log(), args, "ctf") is None
