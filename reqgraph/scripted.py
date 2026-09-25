"""Сценарная модель: отвечает заранее записанными структурами.

Нужна для демо без ключа и для тестов. Проходит тот же путь, что настоящая модель:
with_structured_output → bind_tools → вызов инструмента → разбор PydanticToolsParser.
Отличается только тем, откуда берётся ответ, поэтому граф и проверки работают так же.
"""
from pathlib import Path
from typing import Any

import yaml
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    responses: dict[str, list[dict]] = Field(default_factory=dict)
    calls: list[str] = Field(default_factory=list)
    label: str = "сценарная заглушка"

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        name = convert_to_openai_tool(tools[0])["function"]["name"]
        return self.bind(tool_name=name)

    def _generate(self, messages, stop=None, run_manager=None, tool_name: str | None = None, **kwargs: Any) -> ChatResult:
        queue = self.responses.get(tool_name or "", [])
        if not queue:
            raise LookupError(f"в сценарии не осталось ответа для {tool_name}")
        self.calls.append(tool_name)
        call = {"name": tool_name, "args": queue.pop(0), "id": f"call_{len(self.calls)}", "type": "tool_call"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])


def load_scripted(path: Path) -> ScriptedChatModel:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ScriptedChatModel(
        responses={"Extraction": data.get("extraction", []), "Decomposition": data.get("decomposition", [])},
        label=f"сценарная заглушка {path.parent.name}/{path.name}",
    )
