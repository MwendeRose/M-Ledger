import logging
from transformers import pipeline

logger = logging.getLogger("llm_explainer")

llm = pipeline(
    "text-generation",
    model="google/flan-t5-large",
    max_new_tokens=220,
    temperature=0.45,
    repetition_penalty=1.8
)


def fmt(amount):
    return f"KES {amount:,.2f}"


def explain(data: dict) -> str:
    explanation_type = data.get("type")

    # =====================================================
    # 1) STATEMENT SUMMARY — NUMERIC + FINANCIAL
    # =====================================================
    if explanation_type == "summary":
        prompt = f"""
You are a financial analyst reviewing a Kenyan M-PESA statement.

Statement period: {data['period']}
Total transactions: {data['transaction_count']}
Total income: {fmt(data['total_income'])}
Total expenses: {fmt(data['total_expense'])}
Total charges: {fmt(data['total_charges'])}
Net movement: {fmt(data['net'])}

Using these figures, explain:
- how active the account is
- whether income outweighs spending
- how charges affect the account
- overall financial health

Mention key numbers naturally where relevant.
Write 3–4 analytical sentences.
Financial analysis:
"""

    # =====================================================
    # 2) MIN / MAX — EXPLICIT COMPARISON
    # =====================================================
    elif explanation_type in ["min", "max"]:
        extremum = "lowest" if explanation_type == "min" else "highest"

        prompt = f"""
You are a financial analyst examining Kenyan M-PESA transactions.

The {extremum} {data['metric']} transaction during {data['period']} was
KES {data['amount']:,.2f} on {data['date']}.

Description: {data['details']}

Explain:
- what this transaction represents financially
- how its amount compares to typical transactions
- whether it is unusually small or large

Reference the amount directly in your explanation.
Write 2–3 analytical sentences.
Financial interpretation:
"""

    # =====================================================
    # 3) TOTALS — NUMERIC + TREND AWARE
    # =====================================================
    elif explanation_type == "total":
        tx_count = data.get("transaction_count", "multiple")

        prompt = f"""
You are a financial analyst interpreting Kenyan M-PESA transaction totals.

For the period {data['period']}, the total {data['metric']} amounted to
KES {data['amount']:,.2f} across {tx_count} transactions.

Explain:
- what this total suggests about spending or income behavior
- whether activity is frequent or concentrated
- if the total appears high or moderate for typical M-PESA usage

Use the figures directly to support your analysis.
Write 2–3 insightful sentences.
Financial insight:
"""

    else:
        return "Unable to generate a financial explanation."

    logger.debug(f"LLM prompt:\n{prompt}")

    response = llm(prompt)
    return response[0].get("generated_text", "").strip()