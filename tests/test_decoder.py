"""Unit tests for the OrderFilled decoder."""

from decimal import Decimal

from copytrader.indexer.decoder import decode


def _log(block=100, tx="0x" + "ab" * 32, log_index=0):
    return {
        "blockNumber": block,
        "transactionHash": bytes.fromhex(tx[2:]),
        "logIndex": log_index,
    }


def test_decode_buy_taker_sell_maker():
    # maker provides USDC -> maker is BUYER, taker is SELLER
    log = _log()
    args = {
        "orderHash": bytes.fromhex("ab" * 32),
        "maker": "0xMaker0000000000000000000000000000000000",
        "taker": "0xTaker0000000000000000000000000000000000",
        "makerAssetId": 0,  # USDC
        "takerAssetId": 12345,
        "makerAmountFilled": 30_000_000,  # 30 USDC
        "takerAmountFilled": 100_000_000,  # 100 tokens
        "fee": 0,
    }
    t = decode(log, args, "ctf")
    assert t is not None
    assert t.token_id == "12345"
    # taker provided tokens for USDC -> taker SELL
    assert t.side == "SELL"
    assert t.price == Decimal("0.30000000")
    assert t.size == Decimal("100.000000")
    assert t.notional_usd == Decimal("30.000000")


def test_decode_buy_taker_buy_taker():
    # maker provides tokens -> maker is SELLER, taker is BUYER
    log = _log()
    args = {
        "orderHash": bytes.fromhex("cd" * 32),
        "maker": "0xMaker0000000000000000000000000000000000",
        "taker": "0xTaker0000000000000000000000000000000000",
        "makerAssetId": 9876,
        "takerAssetId": 0,
        "makerAmountFilled": 100_000_000,
        "takerAmountFilled": 70_000_000,
        "fee": 0,
    }
    t = decode(log, args, "negrisk")
    assert t is not None
    assert t.token_id == "9876"
    assert t.side == "BUY"
    assert t.price == Decimal("0.70000000")
    assert t.notional_usd == Decimal("70.000000")


def test_decode_skips_token_to_token():
    args = {
        "orderHash": bytes.fromhex("00" * 32),
        "maker": "0x" + "1" * 40,
        "taker": "0x" + "2" * 40,
        "makerAssetId": 1,
        "takerAssetId": 2,
        "makerAmountFilled": 1,
        "takerAmountFilled": 1,
        "fee": 0,
    }
    assert decode(_log(), args, "ctf") is None
