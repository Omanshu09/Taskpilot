from app.agent.schemas import AgentPlan, AgentTask, ExecutionLog, TaskStatus
from app.document.generator import DocumentGenerator
from app.llm.groq_client import GroqService
from app.tools.registry import ToolRegistry

MAX_RETRIES = 1


class Executor:
    def __init__(self, llm: GroqService, registry: ToolRegistry | None = None, document_generator: DocumentGenerator | None = None):
        self.llm = llm
        self.registry = registry or ToolRegistry()
        self.document_generator = document_generator or DocumentGenerator()

    def execute(self, request: str, plan: AgentPlan) -> tuple[list[ExecutionLog], bytes | None]:
        logs: list[ExecutionLog] = []
        results: dict[str, str] = {}
        document: bytes | None = None
        while any(task.status == TaskStatus.pending for task in plan.tasks):
            eligible = [task for task in plan.tasks if task.status == TaskStatus.pending and all(self._task(plan, dependency).status == TaskStatus.completed for dependency in task.dependencies)]
            if not eligible:
                for task in plan.tasks:
                    if task.status == TaskStatus.pending:
                        task.status = TaskStatus.skipped
                        task.error = "Prerequisite task did not complete"
                break
            task = eligible[0]
            task.status = TaskStatus.running
            logs.append(ExecutionLog(task_id=task.id, event="started", detail=f"Invoking {task.tool}"))
            try:
                output, produced = self._run_with_retry(request, plan, task, results, logs)
            except Exception as exc:
                task.status = TaskStatus.failed
                task.error = str(exc)
                logs.append(ExecutionLog(task_id=task.id, event="failed", detail=task.error))
                if task.required:
                    for remaining in plan.tasks:
                        if remaining.status == TaskStatus.pending:
                            remaining.status = TaskStatus.skipped
                            remaining.error = f"Stopped after required task {task.id} failed"
                    break
                continue
            task.result = output
            task.status = TaskStatus.completed
            results[task.id] = output
            document = produced or document
            logs.append(ExecutionLog(task_id=task.id, event="completed", detail=output[:500]))
        return logs, document

    def _run_with_retry(self, request: str, plan: AgentPlan, task: AgentTask, results: dict[str, str], logs: list[ExecutionLog]) -> tuple[str, bytes | None]:
        while True:
            try:
                return self._run(request, plan, task, results)
            except Exception as exc:
                if task.retry_count >= MAX_RETRIES:
                    raise
                task.retry_count += 1
                logs.append(ExecutionLog(task_id=task.id, event="retrying", detail=str(exc)))

    def _run(self, request: str, plan: AgentPlan, task: AgentTask, results: dict[str, str]) -> tuple[str, bytes | None]:
        needed = {dependency: results[dependency] for dependency in task.dependencies}
        if task.tool == "document":
            sections = self._compose(request, plan, results)
            document = self.document_generator.generate(plan.title, plan.document_type, request, plan.assumptions, sections)
            return f"DOCX created and validated ({len(document)} bytes); sections: {', '.join(s['heading'] for s in sections)}", document
        if task.tool == "analysis":
            return self.registry.get("analysis")(request, plan, task, needed), None
        if task.tool == "calculator":
            raw = self.llm.structured("Write the arithmetic this task needs as JSON with one key, expressions, an array of strings. Each string is a single calculation using only plain numbers, + - * / ** and parentheses, with no units, currency symbols or words. Base every figure on the request, the stated assumptions or prior results.", f"Task: {task.description}\nUser request: {request}\nAssumptions: {plan.assumptions}\nPrior results: {needed}").get("expressions")
            return self.registry.get("calculator")("\n".join(str(item) for item in raw) if isinstance(raw, list) else ""), None
        if task.tool == "writer":
            return self.llm.complete("Write a concise, substantive section for a professional document. Distinguish estimates and assumptions from verified facts. No external research was performed.", f"Document: {plan.document_type}\nUser request: {request}\nTask: {task.description}\nAssumptions: {plan.assumptions}\nPrior results: {needed}"), None
        raise ValueError(f"Unsupported planned tool: {task.tool}")

    def _compose(self, request: str, plan: AgentPlan, results: dict[str, str]) -> list[dict[str, str]]:
        raw = self.llm.structured("Compose the completed material into a professional document outline. Return JSON with sections, an array of objects each having heading and body strings. Use suitable structure for the requested document type. Include practical recommendations and risks when appropriate. Do not invent research or precise facts; label estimates. Write plain text only: no markdown tables or emphasis markers, one paragraph or line per row, bullet lines starting with '- ', and figures as lines such as 'Item: amount'.", f"Title: {plan.title}\nType: {plan.document_type}\nRequest: {request}\nAssumptions: {plan.assumptions}\nTask outputs: {results}")
        sections = raw.get("sections")
        if not isinstance(sections, list) or not sections:
            raise ValueError("Document composition did not return any sections")
        return [{"heading": str(item["heading"]), "body": str(item["body"])} for item in sections if isinstance(item, dict) and item.get("heading") and item.get("body")]

    @staticmethod
    def _task(plan: AgentPlan, task_id: str) -> AgentTask:
        return next(task for task in plan.tasks if task.id == task_id)
