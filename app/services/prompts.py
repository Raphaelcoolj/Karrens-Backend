import json
from typing import Optional


SIGNAL_SYSTEM_PROMPT = """You are Karren, a private AI trading signal analysis system.

Your role is to analyze market data and produce structured trading signals.

CRITICAL RULES:
1. You must ONLY output valid JSON. No text before or after.
2. NEVER output thousands separators in prices (no commas). E.g., use 103450.25, NOT 103,450.25.
3. Preserve decimal precision. E.g., 0.00001247, not 0.
4. Always provide Entry, Stop Loss, Take Profit when direction is LONG or SHORT.
5. Calculate R:R deterministically from the provided levels.
6. Use "reasoning" to explain your analysis clearly.
7. If you see a valid setup with confluence, generate a signal. Do not be overly cautious.
8. When no strategy rules are provided, generate signals based purely on technical analysis confluence.

OUTPUT FORMAT (strict JSON):
{
    "direction": "LONG" | "SHORT" | "NO SIGNAL",
    "confidence": 0-100,
    "entry": number | null,
    "stop_loss": number | null,
    "take_profit": number | null,
    "risk_reward": number | null,
    "reasoning": "string",
    "triggered_conditions": ["string"],
    "invalidating_conditions": ["string"],
    "strategy_alignment": "string" | null,
    "market_context": "string"
}

CONFIDENCE SCORING GUIDELINES:
- 0-20: Very weak, conflicting evidence
- 20-40: Weak, some alignment but significant concerns
- 40-60: Moderate, reasonable alignment with notable caveats
- 60-80: Strong, good confluence across multiple factors
- 80-100: Very strong, exceptional confluence with minimal conflicting evidence

Generate signals when confluence exists. Only output NO SIGNAL when evidence is truly contradictory or data is insufficient.
"""


def build_analysis_prompt(
    pair: str,
    timeframe: str,
    technical_analysis: dict,
    strategy_context: Optional[dict] = None,
    strategy_rules: Optional[dict] = None,
) -> str:
    ta_summary = json.dumps(technical_analysis, indent=2, default=str)

    prompt = f"""Analyze the following market data and produce a trading signal.

PAIR: {pair}
TIMEFRAME: {timeframe}

TECHNICAL ANALYSIS DATA:
{ta_summary}

EVALUATION DIMENSIONS:
1. Market Structure: Assess trend direction, breaks of structure, and structural continuation/reversal.
2. Key Levels: Evaluate support/resistance proximity and significance.
3. Momentum: Assess RSI, MACD, and crossover signals.
4. Volatility: Consider ATR and volatility expansion/contraction.
5. Volume: Assess volume confirmation if data is available.
6. Price Action: Consider recent candle patterns and rejection signals.
7. EMA Alignment: Evaluate trend alignment using moving averages.
"""

    if strategy_rules:
        rules_summary = json.dumps(strategy_rules, indent=2, default=str)
        prompt += f"""
CUSTOM STRATEGY RULES:
{rules_summary}

Apply these strategy rules as a filter. A signal should only be generated if the market conditions satisfy the strategy's entry rules. If the market does not satisfy the strategy, output "NO SIGNAL".

Clearly distinguish between:
- Observations from general market analysis
- Observations from the supplied strategy rules
"""

    if strategy_context:
        strategy_text = strategy_context.get("raw_text", "")[:3000]
        if strategy_text:
            prompt += f"""
STRATEGY REFERENCE TEXT:
{strategy_text}
"""

    prompt += """
NOW EVALUATE:
1. Does the market show a clear directional bias?
2. Is there sufficient confluence across multiple dimensions?
3. Are key levels appropriate for entry, stop loss, and take profit?
4. Is the risk/reward favorable (minimum 1.5:1)?
5. Are there significant conflicting signals?
6. Does the setup meet the strategy rules (if provided)?

If confluence exists and risk/reward is favorable, generate a LONG or SHORT signal.
Only output NO SIGNAL when evidence is truly contradictory or data is insufficient.

Provide your analysis as strictly valid JSON only.
"""

    return prompt
