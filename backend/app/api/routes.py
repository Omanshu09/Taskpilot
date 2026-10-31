from fastapi import APIRouter, Depends, HTTPException

from app.agent.schemas import AgentRequest, AgentResponse
from app.api.limiter import limiter
from app.llm.groq_client import ModelError
from app.services.agent_service import AgentService

router = APIRouter()
service_factory = AgentService


@router.get("/")
def root():
    return {"name": "TaskPilot AI", "description": "Plan, execute, and generate professional Word documents", "docs": "/docs"}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/agent", response_model=AgentResponse, dependencies=[Depends(limiter.check)])
def run_agent(payload: AgentRequest):
    try:
        response = service_factory().run(payload)
    except ModelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if response.status != "completed":
        raise HTTPException(status_code=502, detail={"message": response.message, "plan": [task.model_dump(mode="json") for task in response.plan], "execution_summary": response.execution_summary, "logs": [log.model_dump() for log in response.execution_logs]})
    return response
