from pydantic import ValidationError

from app.agent.schemas import AgentPlan, AgentRequest
from app.llm.groq_client import GroqService, ModelError


class Planner:
    def __init__(self, llm: GroqService):
        self.llm = llm

    def create_plan(self, request: AgentRequest) -> AgentPlan:
        system = "Create a practical execution plan for generating a professional document. Return JSON with document_type, title, assumptions, missing_information, tasks. Each task has id, description, dependencies, tool, required (true or false). Use 3-8 meaningful tasks, unique task_N ids, valid dependency ids. A task only sees the outputs of the tasks listed in its dependencies, so list every earlier task whose output it needs. Tools must be analysis, calculator, writer, or document. Include final document creation as the last task with tool document; it produces a Microsoft Word (.docx) file. Do not claim external research. If the request leaves budget, pricing, team size or technology open, plan tasks that decide them. Any writer task that discusses costs, staffing or pricing must list the calculator task in its dependencies so its figures match the calculation."
        feedback = ""
        reason = ""
        for _ in range(2):
            data = self.llm.structured(system, request.request + feedback)
            try:
                plan = AgentPlan.model_validate(self._normalize(data))
                self._validate_dependencies(plan)
                if any(task.tool not in {"analysis", "calculator", "writer", "document"} for task in plan.tasks):
                    raise ValueError("Plan selected an unregistered tool")
                if plan.tasks[-1].tool != "document":
                    raise ValueError("The final task must generate the document")
                return plan
            except ValueError as exc:
                reason = self._reason(exc)
                feedback = f"\n\nYour previous plan was rejected: {reason}. Return a corrected plan."
        raise ModelError(f"The model returned an invalid plan ({reason}). Please try again.")

    @staticmethod
    def _reason(exc: ValueError) -> str:
        if isinstance(exc, ValidationError):
            return "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()[:3])
        return str(exc)[:300]

    @staticmethod
    def _normalize(data: dict) -> dict:
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            data["tasks"] = [
                {
                    **{key: value for key, value in task.items() if value is not None},
                    "id": str(task.get("id", "")),
                    "dependencies": [str(item) for item in task["dependencies"]] if isinstance(task.get("dependencies"), list) else [],
                    "tool": str(task.get("tool", "")).strip().lower(),
                    "description": str(task.get("description", ""))[:500],
                    "required": str(task.get("required", True)).strip().lower() not in {"false", "no", "0", "optional"},
                }
                for task in tasks
                if isinstance(task, dict)
            ]
        for key in ("assumptions", "missing_information"):
            if isinstance(data.get(key), list):
                data[key] = [str(item) for item in data[key]]
        return data

    @staticmethod
    def _validate_dependencies(plan: AgentPlan) -> None:
        ids = [task.id for task in plan.tasks]
        if len(set(ids)) != len(ids):
            raise ValueError("Plan contains duplicate task IDs")
        known = set(ids)
        for task in plan.tasks:
            if task.id in task.dependencies or not set(task.dependencies).issubset(known):
                raise ValueError("Plan contains invalid dependencies")
        remaining = {task.id: set(task.dependencies) for task in plan.tasks}
        resolved: set[str] = set()
        while remaining:
            available = {task_id for task_id, deps in remaining.items() if deps <= resolved}
            if not available:
                raise ValueError("Plan dependencies contain a cycle")
            resolved.update(available)
            for task_id in available:
                del remaining[task_id]
