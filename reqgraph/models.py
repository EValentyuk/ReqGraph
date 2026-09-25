"""Схемы данных: что модель обязана вернуть и что лежит в состоянии графа."""
import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    """Одно требование. Без источника требования не бывает."""

    id: str = Field(description="Идентификатор вида R1, R2")
    text: str = Field(description="Формулировка: «Система должна…» или «Клиент может…»")
    kind: Literal["functional", "nonfunctional"]
    source: str = Field(
        description="Дословная цитата из запроса или ответа заказчика, "
        "либо ссылка на фрагмент базы знаний вида KB:nfr.idempotency"
    )


class Extraction(BaseModel):
    """Ответ модели на шаге извлечения требований."""

    requirements: list[Requirement]
    questions: list[str] = Field(
        default_factory=list,
        description="Вопросы заказчику: без ответа на них требование не сформулировать проверяемо",
    )


class Task(BaseModel):
    """Задача для разработки со ссылками на требования, которые она закрывает."""

    id: str = Field(description="Идентификатор вида T1")
    title: str
    covers: list[str] = Field(description="Идентификаторы требований, которые закрывает задача")
    acceptance: list[str] = Field(description="Проверяемые критерии приёмки")


class Decomposition(BaseModel):
    """Ответ модели на шаге декомпозиции."""

    epic: str
    tasks: list[Task]


class Issue(BaseModel):
    """Замечание проверки. Их находит код, а не модель."""

    kind: Literal["no_source", "vague", "uncovered", "unknown_ref", "orphan"]
    ref: str
    detail: str


class State(TypedDict, total=False):
    """Состояние графа. Журнал копится редьюсером, остальные поля перезаписываются."""

    request: str
    dialog: list[dict]
    context: list[dict]
    requirements: list[Requirement]
    questions: list[str]
    attempts: int
    source_issues: list[Issue]
    wording_issues: list[Issue]
    issues: list[Issue]
    epic: str
    tasks: list[Task]
    decompose_attempts: int
    coverage_issues: list[Issue]
    document: str
    log: Annotated[list[str], operator.add]
