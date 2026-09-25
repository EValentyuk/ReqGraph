"""Граф: сырой запрос → требования с источниками → вопросы заказчику → задачи с трассировкой.

Модель делает то, что умеет, – формулирует. Всё, что можно проверить без неё, проверяет
код: источник у каждого требования, проверяемость формулировок, покрытие требований
задачами. Найденное уходит модели на доработку, а то, что может решить только заказчик, –
человеку через interrupt.
"""
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, default_retry_on, interrupt
from pydantic import ValidationError

from . import checks, prompts
from .kb import KnowledgeBase
from .models import Decomposition, Extraction, State
from .render import to_markdown

STATE_MODELS = ("Requirement", "Task", "Issue")


def retry_on(exc: Exception) -> bool:
    """Повторять и сетевые сбои, и ответ модели, не прошедший схему.

    Стандартная политика LangGraph ошибки разбора не повторяет: это ValueError.
    """
    return isinstance(exc, (OutputParserException, ValidationError)) or default_retry_on(exc)


LLM_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, retry_on=retry_on)


def make_checkpointer() -> InMemorySaver:
    """Чекпойнтер с явным списком классов, которые разрешено поднимать из сохранённого состояния."""
    serde = JsonPlusSerializer(allowed_msgpack_modules=[("reqgraph.models", name) for name in STATE_MODELS])
    return InMemorySaver(serde=serde)


def model_label(model: BaseChatModel) -> str:
    for attr in ("label", "model_name", "model"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return value
    return type(model).__name__


def build_graph(
    model: BaseChatModel,
    kb: KnowledgeBase,
    *,
    checkpointer=None,
    max_attempts: int = 4,
    retry_policy: RetryPolicy = LLM_RETRY,
):
    extractor = model.with_structured_output(Extraction)
    decomposer = model.with_structured_output(Decomposition)
    label = model_label(model)

    def retrieve(state: State) -> dict:
        text = " ".join([state["request"], *(d["a"] for d in state.get("dialog", []))])
        context = kb.retrieve(text)
        before = {f["id"] for f in state.get("context", [])}
        new = [f["id"] for f in context if f["id"] not in before]
        line = f"retrieve: найдено {len(context)} фрагментов базы знаний"
        if before and new:
            line += ", новые: " + ", ".join(new)
        return {"context": context, "log": [line]}

    def extract(state: State) -> dict:
        attempt = state.get("attempts", 0) + 1
        result = extractor.invoke(prompts.extraction(state))
        if result is None:
            raise OutputParserException("модель не вернула требования в заданной структуре")
        return {
            "requirements": result.requirements,
            "questions": result.questions,
            "attempts": attempt,
            "log": [f"extract, попытка {attempt}: требований {len(result.requirements)}, вопросов {len(result.questions)}"],
        }

    def check_sources(state: State) -> dict:
        answers = [d["a"] for d in state.get("dialog", [])]
        context_ids = [f["id"] for f in state.get("context", [])]
        issues = checks.check_sources(state["requirements"], state["request"], answers, context_ids)
        return {"source_issues": issues, "log": [_line("check_sources", "без источника", issues, "у всех требований есть источник")]}

    def check_wording(state: State) -> dict:
        issues = checks.check_wording(state["requirements"])
        return {"wording_issues": issues, "log": [_line("check_wording", "непроверяемые формулировки", issues, "формулировки проверяемы")]}

    def review(state: State) -> dict:
        issues = [*state.get("source_issues", []), *state.get("wording_issues", [])]
        questions = state.get("questions", [])
        return {"issues": issues, "log": [f"review: замечаний {len(issues)}, вопросов заказчику {len(questions)}"]}

    def route_after_review(state: State) -> str:
        if not state.get("issues") and not state.get("questions"):
            return "decompose"
        if state["attempts"] >= max_attempts:
            return "render"
        return "ask_human" if state.get("questions") else "extract"

    def ask_human(state: State) -> dict:
        # При возобновлении узел выполняется заново с начала, поэтому до interrupt – только чтение.
        questions = state["questions"]
        answers = interrupt({"questions": questions})
        if isinstance(answers, str):
            answers = [answers]
        answers = [*answers, *[""] * max(0, len(questions) - len(answers))]
        dialog = [*state.get("dialog", []), *({"q": q, "a": a.strip()} for q, a in zip(questions, answers))]
        got = sum(1 for a in answers[: len(questions)] if a.strip())
        return {"dialog": dialog, "questions": [], "log": [f"ask_human: ответов {got} из {len(questions)}"]}

    def decompose(state: State) -> dict:
        attempt = state.get("decompose_attempts", 0) + 1
        result = decomposer.invoke(prompts.decomposition(state))
        if result is None:
            raise OutputParserException("модель не вернула задачи в заданной структуре")
        return {
            "epic": result.epic,
            "tasks": result.tasks,
            "decompose_attempts": attempt,
            "log": [f"decompose, попытка {attempt}: задач {len(result.tasks)}"],
        }

    def check_coverage(state: State) -> dict:
        issues = checks.check_coverage(state["requirements"], state["tasks"])
        uncovered = [i.ref for i in issues if i.kind == "uncovered"]
        broken = sorted({i.ref for i in issues if i.kind != "uncovered"}, key=checks.natural_key)
        parts = []
        if uncovered:
            parts.append("без задачи – " + ", ".join(uncovered))
        if broken:
            parts.append("задачи со сломанными ссылками – " + ", ".join(broken))
        line = "check_coverage: " + ("; ".join(parts) if parts else "все требования закрыты задачами")
        return {"coverage_issues": issues, "log": [line]}

    def route_after_coverage(state: State) -> str:
        if state.get("coverage_issues") and state["decompose_attempts"] < max_attempts:
            return "decompose"
        return "render"

    def render(state: State) -> dict:
        return {"document": to_markdown(state, label), "log": ["render: документ собран"]}

    builder = StateGraph(State)
    builder.add_node("retrieve", retrieve)
    builder.add_node("extract", extract, retry_policy=retry_policy)
    builder.add_node("check_sources", check_sources)
    builder.add_node("check_wording", check_wording)
    builder.add_node("review", review)
    builder.add_node("ask_human", ask_human)
    builder.add_node("decompose", decompose, retry_policy=retry_policy)
    builder.add_node("check_coverage", check_coverage)
    builder.add_node("render", render)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "extract")
    # Две независимые проверки идут параллельно, review ждёт обе.
    builder.add_edge("extract", "check_sources")
    builder.add_edge("extract", "check_wording")
    builder.add_edge(["check_sources", "check_wording"], "review")
    builder.add_conditional_edges("review", route_after_review, ["extract", "ask_human", "decompose", "render"])
    builder.add_edge("ask_human", "retrieve")
    builder.add_edge("decompose", "check_coverage")
    builder.add_conditional_edges("check_coverage", route_after_coverage, ["decompose", "render"])
    builder.add_edge("render", END)
    return builder.compile(checkpointer=checkpointer)


def _line(node: str, label: str, issues: list, ok: str) -> str:
    if not issues:
        return f"{node}: {ok}"
    refs = sorted({i.ref for i in issues}, key=checks.natural_key)
    return f"{node}: {label} – {', '.join(refs)}"
