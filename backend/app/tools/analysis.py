from app.agent.schemas import AgentPlan, AgentTask


class StructuredAnalysis:
    def run(self, request: str, plan: AgentPlan, task: AgentTask, prior_results: dict[str, str]) -> str:
        return "\n".join([
            f"Objective: {request}",
            f"Document type: {plan.document_type}",
            f"Focus: {task.description}",
            "Assumptions: " + ("; ".join(plan.assumptions) if plan.assumptions else "None identified by planner"),
            "Information gaps: " + ("; ".join(plan.missing_information) if plan.missing_information else "None identified"),
            "Completed prerequisite outputs: " + ("; ".join(output[:300] for output in prior_results.values()) if prior_results else "None"),
        ])
