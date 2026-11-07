from app.infrastructure.llm.client import complete_json, complete_tools
from app.infrastructure.llm.recording import CallRecording
from app.infrastructure.llm.session import client_session_scope


class OpenAICompatibleModel:
    complete_json = staticmethod(complete_json)
    complete_tools = staticmethod(complete_tools)
    recording = staticmethod(CallRecording)
    session = staticmethod(client_session_scope)
