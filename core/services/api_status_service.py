from __future__ import annotations

from dataclasses import dataclass

from core.services.groq_client import GroqClient


@dataclass(frozen=True)
class ApiHealthStatus:
    state: str
    message: str


class ApiStatusService:
    def __init__(self, groq_client: GroqClient) -> None:
        self.groq_client = groq_client

    def check_health(self) -> ApiHealthStatus:
        try:
            self.groq_client.health_check()
            return ApiHealthStatus(state="ready", message="Groq API is reachable.")
        except Exception as exc:
            return ApiHealthStatus(state="error", message=str(exc))
