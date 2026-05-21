"""Risk management: kill switch + halt conditions + soft limits.

evaluate_risk() is called by the executor before each tick to decide whether
new orders are allowed (fail-closed: any halt condition trips → no new orders).
"""
from copytrader.risk.evaluator import RiskCheck, evaluate_risk

__all__ = ["RiskCheck", "evaluate_risk"]
