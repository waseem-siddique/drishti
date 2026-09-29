"""Optional grounded narration. The model never computes a score or invents evidence."""
from __future__ import annotations
import json, urllib.error, urllib.request
from typing import Any, Dict
from .config import get_settings

DISCLAIMER = ("This is a risk signal and should be verified. It does not establish fraud or "
              "misconduct.")
SYSTEM_PROMPT = ("You explain pre-computed risk results for public works oversight. Use only the "
                 "structured data supplied. Never invent numbers, evidence, peer statistics or "
                 "conclusions, and never state that fraud occurred.")


def model_metadata() -> Dict[str, Any]:
    settings = get_settings()
    return {"provider": settings.llm_provider, "model": settings.llm_model,
            "enabled": settings.llm_enabled,
            "role": "Explanation only. Risk scoring is deterministic and model-independent."}


def deterministic_explanation(dossier: Dict[str, Any]) -> str:
    score = dossier.get("risk", {})
    lines = [f"Work {dossier.get('work_id')} scored {score.get('risk_score')} "
             f"({score.get('risk_band')} risk) with confidence "
             f"{score.get('confidence_score')}. Priority: {score.get('priority_label')}."]
    for factor in (dossier.get("factors") or [])[:5]:
        lines.append(f"- {factor.get('rule_id')}: {factor.get('statement')} "
                     f"(+{factor.get('weighted_contribution')} points)")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def explain(dossier: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    metadata = model_metadata()
    fallback = {"explanation": deterministic_explanation(dossier), "source": "deterministic",
                "model": metadata, "disclaimer": DISCLAIMER}
    if not settings.llm_enabled or settings.llm_provider != "anthropic":
        fallback["warning"] = ("No language model is configured, so the deterministic summary is "
                               "shown. The product is fully functional without it.")
        return fallback
    body = json.dumps({
        "model": settings.llm_model, "max_tokens": 700, "system": SYSTEM_PROMPT,
        "messages": [{"role": "user",
                      "content": "Summarise this risk dossier for a verification officer in "
                                 "plain language.\n" + json.dumps(dossier, default=str)}],
    }).encode()
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": settings.llm_api_key,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode())
        text = "".join(block.get("text", "") for block in payload.get("content", []))
        return {"explanation": text.strip() or fallback["explanation"], "source": "llm",
                "model": metadata, "disclaimer": DISCLAIMER}
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        fallback["warning"] = f"The language model could not be reached ({exc})."
        return fallback
