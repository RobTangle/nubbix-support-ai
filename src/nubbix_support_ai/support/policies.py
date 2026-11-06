from nubbix_support_ai.support.contracts import SupportResponse


def safe_response() -> SupportResponse:
    return SupportResponse(
        answer="Tu consulta requiere revisión por un agente humano para poder ayudarte con seguridad.",
        confidence=0.0, category="other", actions=["Derivar la consulta a soporte humano."],
    )


def suggest_review(proposal: SupportResponse) -> SupportResponse:
    if proposal.confidence >= 0.70:
        return proposal
    actions = [*proposal.actions[:4], "Solicitar revisión humana antes de responder."]
    return SupportResponse.model_validate(proposal.model_dump() | {"actions": actions})
