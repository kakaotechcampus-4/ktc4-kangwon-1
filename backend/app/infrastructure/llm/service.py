from app.infrastructure.config import BACKEND_DIR
from app.infrastructure.llm.client import complete_json, complete_tools
from app.infrastructure.llm.recording import CallRecording
from app.infrastructure.llm.session import client_session_scope


class OpenAICompatibleModel:
    complete_json = staticmethod(complete_json)
    complete_tools = staticmethod(complete_tools)
    session = staticmethod(client_session_scope)

    @staticmethod
    def recording(request_id, path=None):
        return CallRecording(path or BACKEND_DIR / "cache" / f"{request_id}-model-calls.json")
