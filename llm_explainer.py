import logging
from transformers import pipeline

logger = logging.getLogger("llm_explainer")

llm = pipeline(
    "text-generation",
    model="google/flan-t5-large",
    max_new_tokens=180,
    temperature=0.4
)


def explain(data: dict) -> str:
    logger.debug(f"Received data for explanation: {data}")

    explanation_type = data.get("type")

    # =====================================================
    # SUMMARY PROMPT (FINANCIAL ANALYST STYLE)
    # =====================================================
    if explanation_type == "summary":
        prompt = (
            f"You are a financial analyst reviewing a mobile money statement.\n\n"
            f"Statement period: {data['period']}.\n"
            f"Total transactions: {data['transaction_count']}.\n"
            f"Total income: KES {data['total_income']}.\n"
            f"Total expenses: KES {data['total_expense']}.\n"
            f"Total charges: KES {data['total_charges']}.\n"
            f"Net balance: KES {data['net']}.\n\n"
            f"Write 3–4 sentences explaining the financial behavior, "
            f"spending patterns, and overall account health."
        )

    # =====================================================
    # MIN / MAX PROMPT
    # =====================================================
    elif explanation_type in ["min", "max"]:
        extremum = "lowest" if explanation_type == "min" else "highest"

        prompt = (
            f"You are a financial analyst examining transaction records.\n\n"
            f"The {extremum} {data['metric']} transaction occurred during {data['period']}.\n"
            f"Amount: KES {data['amount']}.\n"
            f"Date: {data['date']}.\n"
            f"Description: {data['details']}.\n\n"
            f"Explain what this transaction represents financially, "
            f"and why this value is significant in the context of overall activity."
        )

    # =====================================================
    # TOTALS PROMPT
    # =====================================================
    elif explanation_type == "total":
        prompt = (
            f"You are a financial analyst summarizing transaction totals.\n\n"
            f"Metric: {data['metric']}.\n"
            f"Total amount: KES {data['amount']}.\n"
            f"Period: {data['period']}.\n\n"
            f"Explain what this total indicates about the user's financial activity, "
            f"including possible spending or income trends."
        )

    else:
        return "Unable to generate explanation for the requested action."

    logger.debug(f"Calling LLM with prompt:\n{prompt}")

    response = llm(prompt)

    generated = response[0].get("generated_text", "").strip()

    logger.info("Explanation generated successfully")

    return generated
