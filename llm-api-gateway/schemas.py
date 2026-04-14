from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: float | None = 0.7
    top_p: float | None = 1.0
    max_tokens: int | None = None
    stream: bool = False
    stop: str | list[str] | None = None
    frequency_penalty: float | None = 0.0
    presence_penalty: float | None = 0.0


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatMessage(BaseModel):
    role: str
    content: str


class Choice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


class ModelList(BaseModel):
    object: str = "list"
    data: list[dict]
