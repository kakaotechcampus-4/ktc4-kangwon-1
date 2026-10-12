"""기존 완성 응답 시험 자료를 SSE 응답으로 전송합니다."""

import copy
import json

import httpx


def stream_response(status=200, *, json):
    if status != 200:
        return httpx.Response(status, json=json)
    chunk = copy.deepcopy(json)
    chunk["object"] = "chat.completion.chunk"
    choices = chunk.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if isinstance(choice, dict):
                delta = choice.pop("message", {})
                for index, tool in enumerate(delta.get("tool_calls") or []):
                    tool["index"] = index
                choice["delta"] = delta
    return sse_response([chunk])


def sse_response(chunks):
    content = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
    return httpx.Response(
        200, text=content + "data: [DONE]\n\n", headers={"content-type": "text/event-stream"}
    )
