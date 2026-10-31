from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class AgentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    request: str = Field(min_length=12, max_length=12000)


class AgentTask(BaseModel):
    id: str
    description: str = Field(min_length=4, max_length=500)
    status: TaskStatus = TaskStatus.pending
    dependencies: list[str] = Field(default_factory=list)
    tool: str
    required: bool = True
    result: str | None = None
    retry_count: int = 0
    error: str | None = None


class AgentPlan(BaseModel):
    document_type: str
    title: str
    tasks: list[AgentTask] = Field(min_length=2, max_length=12)
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class TaskResult(BaseModel):
    task_id: str
    tool: str
    success: bool
    output: str
    error: str | None = None


class ExecutionLog(BaseModel):
    task_id: str
    event: str
    detail: str


class AgentResponse(BaseModel):
    status: str
    message: str
    document_type: str
    plan: list[AgentTask]
    assumptions: list[str]
    execution_summary: dict[str, int]
    execution_logs: list[ExecutionLog]
    document: dict[str, str] | None = None
