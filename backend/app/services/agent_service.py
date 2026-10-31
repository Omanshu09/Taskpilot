import base64
import re

from app.agent.executor import Executor
from app.agent.planner import Planner
from app.agent.schemas import AgentRequest, AgentResponse, TaskStatus
from app.llm.groq_client import GroqService


class AgentService:
    def __init__(self, llm: GroqService | None = None):
        self.llm = llm or GroqService()
        self.planner = Planner(self.llm)
        self.executor = Executor(self.llm)

    def run(self, request: AgentRequest) -> AgentResponse:
        plan = self.planner.create_plan(request)
        logs, payload = self.executor.execute(request.request, plan)
        complete = payload is not None and all(task.status == TaskStatus.completed for task in plan.tasks)
        completed = sum(task.status == TaskStatus.completed for task in plan.tasks)
        failed = sum(task.status == TaskStatus.failed for task in plan.tasks)
        document = None
        if payload:
            stem = re.sub(r"[^a-z0-9]+", "_", plan.title.lower()).strip("_")[:60] or "taskpilot_document"
            document = {"filename": f"{stem}.docx", "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "base64": base64.b64encode(payload).decode("ascii")}
        return AgentResponse(status="completed" if complete else "failed", message="Your document has been generated and validated." if complete else "Execution did not complete. Review task results and try again.", document_type=plan.document_type, plan=plan.tasks, assumptions=plan.assumptions, execution_summary={"total_tasks": len(plan.tasks), "completed_tasks": completed, "failed_tasks": failed}, execution_logs=logs, document=document)
