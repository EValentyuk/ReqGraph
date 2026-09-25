"""Тексты для модели.

Правило в промпте – просьба. Гарантию даёт проверка в checks.py, поэтому здесь
правил ровно столько, чтобы модель реже ошибалась, а не чтобы не ошибалась никогда.
"""
from langchain_core.messages import HumanMessage, SystemMessage

EXTRACT_RULES = """Ты системный аналитик банка. Выдели требования из запроса заказчика.

Правила:
- одно требование – одна проверяемая мысль, формулировка «Система должна…» или «Клиент может…»;
- поле source – дословная цитата из запроса или из ответа заказчика, либо ссылка KB:<id> на фрагмент базы знаний. Без источника требование не пиши;
- не придумывай значений, которых нет в источниках: сумм, сроков, лимитов. Если без значения требование не проверить – задай вопрос в questions;
- не используй непроверяемых слов: быстро, удобно, корректно, надёжно, оптимально, по возможности;
- термины бери из глоссария базы знаний."""

DECOMPOSE_RULES = """Ты системный аналитик. Разложи требования на эпик и задачи для разработки.

Правила:
- каждая задача закрывает одно или несколько требований, их id перечисли в covers;
- каждое требование закрыто хотя бы одной задачей;
- у задачи два-четыре проверяемых критерия приёмки;
- задачи режь так, чтобы каждую можно было сдать отдельно;
- не добавляй в критерии поведения, которого нет в требованиях."""


def extraction(state: dict) -> list:
    parts = [f"Запрос заказчика:\n{state['request']}"]
    if state.get("dialog"):
        parts.append(
            "Ответы заказчика на вопросы:\n"
            + "\n".join(f"- {d['q']} Ответ: {d['a'] or 'нет ответа'}" for d in state["dialog"])
        )
    if state.get("context"):
        parts.append("База знаний, найденные фрагменты:\n" + "\n".join(f"[KB:{f['id']}] {f['text']}" for f in state["context"]))
    if state.get("requirements"):
        parts.append(
            "Прошлая версия требований:\n"
            + "\n".join(f"{r.id}. {r.text} [источник: {r.source}]" for r in state["requirements"])
        )
    if state.get("issues"):
        parts.append("Замечания проверки к прошлой версии – исправь их:\n" + "\n".join(f"- {i.ref}: {i.detail}" for i in state["issues"]))
    return [SystemMessage(EXTRACT_RULES), HumanMessage("\n\n".join(parts))]


def decomposition(state: dict) -> list:
    parts = ["Требования:\n" + "\n".join(f"{r.id}. {r.text}" for r in state["requirements"])]
    if state.get("coverage_issues"):
        previous = "\n".join(f"{t.id}. {t.title} – закрывает {', '.join(t.covers)}" for t in state.get("tasks", []))
        issues = "\n".join(f"- {i.ref}: {i.detail}" for i in state["coverage_issues"])
        parts.append(f"Прошлая версия задач:\n{previous}\n\nЗамечания проверки – исправь их:\n{issues}")
    return [SystemMessage(DECOMPOSE_RULES), HumanMessage("\n\n".join(parts))]
