from __future__ import annotations


class OrchestratorError(Exception):
    def __init__(self, message: str, *, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AgentCallError(OrchestratorError):
    def __init__(self, agent_name: str, message: str, *, status_code: int = 502):
        super().__init__(message, status_code=status_code)
        self.agent_name = agent_name


class MissingDependencyError(OrchestratorError):
    def __init__(self, dependency: str, message: str | None = None):
        super().__init__(
            message or f"Required dependency '{dependency}' is not enabled yet.",
            status_code=424,
        )
        self.dependency = dependency


class SessionNotFoundError(OrchestratorError):
    def __init__(self, session_id: str):
        super().__init__(f"Counselling session '{session_id}' was not found.", status_code=404)
        self.session_id = session_id
