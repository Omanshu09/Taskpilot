from app.agent.schemas import AgentPlan, AgentRequest
from app.llm.groq_client import GroqService, ModelError


class Planner:
    def __init__(self, llm: GroqService):
        self.llm = llm

    def create_plan(self, request: AgentRequest) -> AgentPlan:
        system = "Create a practical execution plan for generating a professional document. Return JSON with document_type, title, assumptions, missing_information, tasks. Each task has id, description, dependencies, tool, required. Use 3-8 meaningful tasks, unique task_N ids, valid dependency ids. A task only sees the outputs of the tasks listed in its dependencies, so list every earlier task whose output it needs. Tools must be analysis, calculator, writer, or document. Include final document creation as the last task with tool document. Do not claim external research."
        feedback = ""
        for _ in range(2):
            data = self.llm.structured(system, request.request + feedback)
            try:
                plan = AgentPlan.model_validate(data)
                self._validate_dependencies(plan)
                if any(task.tool not in {"analysis", "calculator", "writer", "document"} for task in plan.tasks):
                    raise ValueError("Plan selected an unregistered tool")
                if plan.tasks[-1].tool != "document":
                    raise ValueError("The final task must generate the document")
                return plan
            except ValueError as exc:
                feedback = f"\n\nYour previous plan was rejected: {str(exc)[:300]}. Return a corrected plan."
        raise ModelError("The model returned an invalid plan. Please try again.")

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
