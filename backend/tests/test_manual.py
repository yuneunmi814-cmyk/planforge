"""Manual handoff: assemble a pastable prompt, and import a pasted chat response
into a project — reusing the same prompt + output-contract parser as the worker."""

import json

from app.models import SECTION_TYPES
from app.services.llm import FakeLLMClient
from tests.conftest import auth_headers


def _valid_paste(idea: str = "동네 헬스장 SaaS") -> str:
    """A valid output-contract payload — exactly what a chat would return."""
    return FakeLLMClient().complete(
        system="", user=f"<user_idea>\n{idea}\n</user_idea>", temperature=0.4, max_tokens=100
    )


def test_manual_prompt_contains_system_and_idea(client):
    headers = auth_headers(client)
    res = client.post("/api/v1/manual/prompt", json={"idea": "동네 헬스장 SaaS"}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert "<user_idea>" in body["prompt"]
    assert "동네 헬스장 SaaS" in body["prompt"]
    assert body["promptVersion"]  # content-hash version present


def test_manual_import_creates_project_with_all_sections(client):
    headers = auth_headers(client)
    res = client.post(
        "/api/v1/manual/import",
        json={"idea": "동네 헬스장 SaaS", "text": _valid_paste()},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    pid = body["projectId"]
    # The imported project renders like any other: all 13 sections in spec order.
    detail = client.get(f"/api/v1/projects/{pid}", headers=headers).json()
    assert [s["type"] for s in detail["sections"]] == list(SECTION_TYPES)
    # Export works on it too (it's a normal project).
    assert client.get(f"/api/v1/projects/{pid}/export?format=md", headers=headers).status_code == 200


def test_manual_import_tolerates_prose_wrapped_json(client):
    headers = auth_headers(client)
    paste = "물론이죠! 요청하신 기획서입니다:\n\n" + _valid_paste() + "\n\n도움이 되었길 바랍니다."
    res = client.post("/api/v1/manual/import", json={"idea": "x", "text": paste}, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "success"


def test_manual_import_passes_through_rejection(client):
    headers = auth_headers(client)
    rejected = json.dumps({"status": "rejected", "reason": "유해한 요청"}, ensure_ascii=False)
    res = client.post("/api/v1/manual/import", json={"idea": "x", "text": rejected}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "rejected"
    assert body["projectId"] is None


def test_manual_import_garbage_is_422(client):
    headers = auth_headers(client)
    res = client.post(
        "/api/v1/manual/import", json={"idea": "x", "text": "이건 JSON이 아니에요"}, headers=headers
    )
    assert res.status_code == 422
