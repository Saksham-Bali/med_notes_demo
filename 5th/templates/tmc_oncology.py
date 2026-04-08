from .nabh_standard import TEMPLATE_GUIDANCE as NABH_STANDARD_GUIDANCE

TEMPLATE_GUIDANCE = f"""
{NABH_STANDARD_GUIDANCE}

Additional TMC oncology requirements:
- Prefer oncology terminology for diagnoses, procedures, and toxicities.
- Include chemotherapy and radiation details only when explicitly supported.
- If RECIST data is present, state the response category and summarize measurable trends.
- Keep counselling content limited to the approved counselling facts.
""".strip()
