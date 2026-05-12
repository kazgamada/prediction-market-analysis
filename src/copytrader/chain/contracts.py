"""Polymarket contract addresses and event ABIs on Polygon.

V2 contracts (post-2026 migration):
- CTFExchangeV2: 0xE111180000d2663C0091e4f400237545B87B996B
- NegRiskCtfExchangeV2: 0xe2222d279d744050d28e00520010520000310F59

V1 contracts (legacy, no longer emit new OrderFilled events):
- CTFExchange (V1): 0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
- NegRiskCtfExchange (V1): 0xC5d563A36AE78145C45a50134d48A1215220f80a

V2 OrderFilled signature changed and so did the topic hash and field set:
- V1: (bytes32 orderHash, address maker, address taker, uint256 makerAssetId,
       uint256 takerAssetId, uint256 makerAmountFilled, uint256 takerAmountFilled,
       uint256 fee)
- V2: (bytes32 orderHash, address maker, address taker, uint8 side,
       uint256 tokenId, uint256 makerAmountFilled, uint256 takerAmountFilled,
       uint256 fee, bytes32 builder, bytes32 metadata)

V2 では asset id pair (USDC=0 / token id) ではなく、`side` (0=BUY / 1=SELL maker pov)
と `tokenId` で取引方向を表す。
"""

CTF_EXCHANGE = "0xE111180000d2663C0091e4f400237545B87B996B"
NEGRISK_CTF_EXCHANGE = "0xe2222d279d744050d28e00520010520000310F59"

# 旧 V1 アドレス。historical backfill (block < ~86700000 付近) を再取り込み
# したい場合のみ参照する。新規 trade は出ない。
CTF_EXCHANGE_V1 = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEGRISK_CTF_EXCHANGE_V1 = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

EXCHANGES = {
    "ctf": CTF_EXCHANGE,
    "negrisk": NEGRISK_CTF_EXCHANGE,
}

# keccak256("OrderFilled(bytes32,address,address,uint8,uint256,uint256,uint256,uint256,bytes32,bytes32)")
ORDER_FILLED_TOPIC = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"

ORDER_FILLED_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "orderHash", "type": "bytes32"},
        {"indexed": True, "name": "maker", "type": "address"},
        {"indexed": True, "name": "taker", "type": "address"},
        {"indexed": False, "name": "side", "type": "uint8"},
        {"indexed": False, "name": "tokenId", "type": "uint256"},
        {"indexed": False, "name": "makerAmountFilled", "type": "uint256"},
        {"indexed": False, "name": "takerAmountFilled", "type": "uint256"},
        {"indexed": False, "name": "fee", "type": "uint256"},
        {"indexed": False, "name": "builder", "type": "bytes32"},
        {"indexed": False, "name": "metadata", "type": "bytes32"},
    ],
    "name": "OrderFilled",
    "type": "event",
}

USDC_DECIMALS = 6
TOKEN_DECIMALS = 6  # CTF outcome tokens use 6 decimals on Polymarket

# Gnosis Conditional Tokens Framework on Polygon (used for outcome ERC-1155 balances)
CONDITIONAL_TOKENS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"

CTF_BALANCE_OF_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "id", "type": "uint256"},
        ],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]
