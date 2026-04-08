from .nabh_standard import TEMPLATE_GUIDANCE as NABH_STANDARD_GUIDANCE
from .tmc_oncology import TEMPLATE_GUIDANCE as TMC_ONCOLOGY_GUIDANCE

TEMPLATES = {
    "nabh_standard": NABH_STANDARD_GUIDANCE,
    "tmc_oncology": TMC_ONCOLOGY_GUIDANCE,
}


def get_template_guidance(name: str) -> str:
    try:
        return TEMPLATES[name]
    except KeyError as exc:
        available_templates = ", ".join(sorted(TEMPLATES))
        raise ValueError(
            f"Unsupported template '{name}'. Available templates: {available_templates}."
        ) from exc
