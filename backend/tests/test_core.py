import io
import zipfile
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agent.executor import Executor
from app.agent.planner import Planner
from app.agent.schemas import AgentPlan, AgentRequest, TaskStatus
from app.api.limiter import RateLimiter
from app.document.generator import DocumentGenerator
from app.llm.groq_client import GroqService, ModelError
from app.main import app
from app.services.agent_service import AgentService
from app.tools.calculator import Calculator
from app.tools.registry import ToolRegistry


class FakeLLM:
    def structured(self, system, user):
        if "execution plan" in system:
            title = "Proposal" if "coffee" in user.lower() else "Technical Plan"
            return {"document_type": "Business Proposal" if "coffee" in user.lower() else "Technical Project Plan", "title": title, "assumptions": ["Costs are planning estimates."], "missing_information": ["Exact budget not provided."], "tasks": [{"id": "task_1", "description": "Analyze requirements", "dependencies": [], "tool": "analysis"}, {"id": "task_2", "description": "Draft proposal sections", "dependencies": ["task_1"], "tool": "writer"}, {"id": "task_3", "description": "Create final document", "dependencies": ["task_2"], "tool": "document"}]}
        return {"sections": [{"heading": "Executive Summary", "body": "A concise plan based on the stated requirements."}, {"heading": "Risks and Recommendations", "body": "Validate assumptions before committing funds."}]}

    def complete(self, system, user, json_mode=False):
        return "Draft material grounded in the user request and stated assumptions."


def test_request_validation():
    with pytest.raises(ValueError):
        AgentRequest(request="   ")
    with pytest.raises(ValueError):
        AgentRequest(request="short" + " " * 20)
    assert AgentRequest(request="  Create a project plan  ").request == "Create a project plan"


def test_dynamic_plan_and_dependency_validation():
    planner = Planner(FakeLLM())
    first = planner.create_plan(AgentRequest(request="Coffee business proposal for Almora"))
    second = planner.create_plan(AgentRequest(request="Online learning technical project plan"))
    assert first.document_type != second.document_type
    assert first.tasks[1].dependencies == ["task_1"]
    assert second.tasks[-1].tool == "document"
    with pytest.raises(ValueError):
        planner._validate_dependencies(AgentPlan(document_type="X", title="X", tasks=[{"id": "a", "description": "Task A", "tool": "analysis", "dependencies": ["b"]}, {"id": "b", "description": "Task B", "tool": "document", "dependencies": ["a"]}]))


def test_calculator_and_registry():
    assert "500.00" in Calculator().calculate("100 + 200 * 2")
    assert "840,000.00" in Calculator().calculate("(50,000 + 20,000) * 12")
    assert "could not be evaluated" in Calculator().calculate("Launch in 2026")
    assert "no calculation was performed" in Calculator().calculate("")
    assert ToolRegistry().get("analysis")
    with pytest.raises(KeyError):
        ToolRegistry().get("unregistered")


def test_document_integrity():
    payload = DocumentGenerator().generate("Example Plan", "Project Plan", "Make a plan", ["Budget is assumed"], [{"heading": "Overview", "body": "First item\nSecond item"}])
    assert zipfile.is_zipfile(io.BytesIO(payload))


def test_document_renders_markdown_lines():
    body = "Plain **bold** text\n- First point\n* Second point\n## Costs"
    payload = DocumentGenerator().generate("Example Plan", "Project Plan", "Make a plan", [], [{"heading": "Overview", "body": body}])
    paragraphs = Document(io.BytesIO(payload)).paragraphs
    texts = [p.text for p in paragraphs]
    assert "Plain bold text" in texts
    assert "First point" in texts and "Second point" in texts
    assert next(p for p in paragraphs if p.text == "First point").style.name == "List Bullet"
    assert next(p for p in paragraphs if p.text == "Costs").style.name == "Heading 2"
    assert not any("**" in text for text in texts)


def test_planner_rejects_invalid_plan_as_model_error():
    class BadPlanLLM(FakeLLM):
        def structured(self, system, user):
            return {"document_type": "X", "title": "X", "tasks": [{"id": "task_1", "description": "Only task", "dependencies": [], "tool": "writer"}]}

    with pytest.raises(ModelError):
        Planner(BadPlanLLM()).create_plan(AgentRequest(request="Coffee business proposal for Almora"))


def test_executor_runs_calculator_with_model_expressions():
    class MathLLM(FakeLLM):
        def structured(self, system, user):
            if "arithmetic" in system:
                return {"expressions": ["(1000 + 500) * 12"]}
            return super().structured(system, user)

    plan = AgentPlan(document_type="Plan", title="Plan", tasks=[{"id": "task_1", "description": "Estimate annual cost", "tool": "calculator", "dependencies": []}, {"id": "task_2", "description": "Create final document", "tool": "document", "dependencies": ["task_1"]}])
    logs, document = Executor(MathLLM()).execute("Estimate annual cost", plan)
    assert "18,000.00" in plan.tasks[0].result
    assert plan.tasks[1].status == TaskStatus.completed
    assert document is not None


def test_executor_preserves_failure_and_skips_dependents():
    class BrokenWriter(FakeLLM):
        def complete(self, system, user, json_mode=False):
            raise RuntimeError("provider unavailable")

    plan = Planner(FakeLLM()).create_plan(AgentRequest(request="Coffee business proposal for Almora"))
    logs, document = Executor(BrokenWriter()).execute("Coffee business proposal", plan)
    assert plan.tasks[1].status == TaskStatus.failed
    assert plan.tasks[2].status == TaskStatus.skipped
    assert document is None
    assert any(log.event == "failed" for log in logs)


def groq_with(outcomes):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))])

    service = GroqService(api_key="test-key")
    service.backoff_seconds = 0
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return service, calls


def test_groq_retries_rate_limit_then_succeeds():
    service, calls = groq_with([RuntimeError("Error code: 429 rate limit"), RuntimeError("Error code: 429 rate limit"), "done"])
    assert service.complete("system", "user") == "done"
    assert len(calls) == 3


def test_groq_gives_up_after_repeated_rate_limits():
    service, calls = groq_with([RuntimeError("Error code: 429 rate limit")])
    with pytest.raises(ModelError, match="rate limit"):
        service.complete("system", "user")
    assert len(calls) == service.attempts


def test_groq_does_not_retry_other_errors():
    service, calls = groq_with([RuntimeError("connection refused")])
    with pytest.raises(ModelError, match="could not complete"):
        service.complete("system", "user")
    assert len(calls) == 1


def test_planner_retries_once_with_feedback():
    class FlakyPlanner(FakeLLM):
        prompts = []

        def structured(self, system, user):
            self.prompts.append(user)
            if len(self.prompts) == 1:
                return {"document_type": "X", "title": "X", "tasks": []}
            return super().structured(system, user)

    llm = FlakyPlanner()
    plan = Planner(llm).create_plan(AgentRequest(request="Coffee business proposal for Almora"))
    assert plan.tasks[-1].tool == "document"
    assert len(llm.prompts) == 2 and "rejected" in llm.prompts[1]


def test_executor_retries_a_failed_task_once():
    class FlakyWriter(FakeLLM):
        calls = 0

        def complete(self, system, user, json_mode=False):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return "Recovered draft"

    plan = Planner(FakeLLM()).create_plan(AgentRequest(request="Coffee business proposal for Almora"))
    logs, document = Executor(FlakyWriter()).execute("Coffee business proposal", plan)
    assert plan.tasks[1].status == TaskStatus.completed
    assert plan.tasks[1].retry_count == 1
    assert any(log.event == "retrying" for log in logs)
    assert document is not None


def test_task_only_receives_declared_dependency_outputs():
    class Recording(FakeLLM):
        prompts = {}

        def complete(self, system, user, json_mode=False):
            label = "alpha" if "Draft A" in user else "beta"
            self.prompts[label] = user
            return "ALPHA-OUTPUT" if label == "alpha" else "BETA-OUTPUT"

    llm = Recording()
    plan = AgentPlan(document_type="Plan", title="Plan", tasks=[{"id": "task_1", "description": "Draft A", "tool": "writer", "dependencies": []}, {"id": "task_2", "description": "Draft B", "tool": "writer", "dependencies": []}, {"id": "task_3", "description": "Create final document", "tool": "document", "dependencies": ["task_1", "task_2"]}])
    Executor(llm).execute("Make a plan", plan)
    assert "ALPHA-OUTPUT" not in llm.prompts["beta"]
    assert plan.tasks[2].status == TaskStatus.completed


def test_rate_limiter_blocks_after_limit():
    limiter = RateLimiter(2)
    request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"))
    limiter.check(request)
    limiter.check(request)
    with pytest.raises(HTTPException) as caught:
        limiter.check(request)
    assert caught.value.status_code == 429
    limiter.check(SimpleNamespace(client=SimpleNamespace(host="10.0.0.2")))


def test_api_health_and_validation():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/agent", json={"request": "bad"}).status_code == 422


def test_api_model_failure_is_safe(monkeypatch):
    class FailedService:
        def run(self, payload):
            raise ModelError("Groq rate limit reached. Please retry shortly.")

    monkeypatch.setattr("app.api.routes.service_factory", FailedService)
    response = TestClient(app).post("/agent", json={"request": "Create a technical project plan for a learning platform."})
    assert response.status_code == 502
    assert response.json()["detail"] == "Groq rate limit reached. Please retry shortly."


@pytest.mark.parametrize("prompt", [
    "Create a professional business proposal for launching a small coffee shop in Almora, Uttarakhand. Include an executive summary, target market, estimated investment, operational plan, marketing strategy and financial projections.",
    "Prepare a technical project plan for building an AI-powered online learning platform for college students. I have a limited budget and want to launch within six months. Include the technology stack, development phases, team requirements, estimated costs, risks and a launch strategy. Make reasonable assumptions wherever information is missing.",
])
def test_required_scenarios_through_agent_endpoint(monkeypatch, prompt):
    monkeypatch.setattr("app.api.routes.service_factory", lambda: AgentService(FakeLLM()))
    response = TestClient(app).post("/agent", json={"request": prompt})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["execution_summary"]["completed_tasks"] == 3
    assert body["document"]["base64"].startswith("UEs")
