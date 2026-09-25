"""Итоговый документ: требования с источниками, вопросы заказчику, задачи и трассировка."""
from .checks import natural_key

KIND = {"functional": "ФТ", "nonfunctional": "НФТ"}


def to_markdown(state: dict, model_label: str) -> str:
    requirements = state.get("requirements", [])
    tasks = state.get("tasks", [])
    lines = [
        f"# {state.get('epic') or 'Требования'}",
        "",
        f"*Собрано графом ReqGraph. Модель: {model_label}. "
        f"Попыток извлечения требований: {state.get('attempts', 0)}, "
        f"декомпозиции: {state.get('decompose_attempts', 0)}.*",
        "",
        "## Запрос заказчика",
        "",
        *[f"> {line}" for line in state["request"].splitlines()],
        "",
    ]
    if state.get("dialog"):
        lines += ["## Уточнения у заказчика", "", "| **Вопрос** | **Ответ** |", "|:---|:---|"]
        lines += [f"| {_cell(d['q'])} | {_cell(d['a']) or 'нет ответа'} |" for d in state["dialog"]]
        lines.append("")
    if state.get("context"):
        lines += ["## Найдено в базе знаний", "", "| **Фрагмент** | **По словам** |", "|:---|:---|"]
        lines += [f"| `{f['id']}` | {', '.join(f['matched'])} |" for f in state["context"]]
        lines.append("")
    lines += ["## Требования", "", "| **ID** | **Требование** | **Тип** | **Источник** |", "|:---|:---|:---|:---|"]
    lines += [f"| {r.id} | {_cell(r.text)} | {KIND[r.kind]} | {_source(r.source)} |" for r in requirements]
    lines.append("")

    open_items = [f"{i.ref}: {i.detail}" for i in [*state.get("issues", []), *state.get("coverage_issues", [])]]
    open_items += [f"вопрос без ответа: {q}" for q in state.get("questions", [])]
    if open_items:
        lines += ["## Не закрыто", "", *_bullets(open_items), ""]

    if tasks:
        lines += ["## Задачи", ""]
        for task in tasks:
            lines += [f"### {task.id}. {task.title}", "", f"Закрывает: {', '.join(task.covers)}.", ""]
            lines += ["Критерии приёмки:", "", *_bullets(task.acceptance), ""]
        lines += ["## Трассировка: требование → задачи", "", "| **Требование** | **Задачи** |", "|:---|:---|"]
        for req in sorted(requirements, key=lambda r: natural_key(r.id)):
            covering = [t.id for t in tasks if req.id in t.covers]
            lines.append(f"| {req.id} | {', '.join(covering) or '–'} |")
        lines.append("")

    lines += ["## Журнал прогона", "", *[f"{n}. {line}" for n, line in enumerate(state.get("log", []), 1)], ""]
    return "\n".join(lines)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").strip()


def _source(source: str) -> str:
    if source.upper().startswith("KB:"):
        return f"база знаний `{source[3:].strip()}`"
    return f"«{_cell(source)}»"


def _bullets(items: list[str]) -> list[str]:
    """Пункты после двоеточия: со строчной буквы, через точку с запятой, последний – с точкой."""
    cleaned = [_lower_first(item.strip().rstrip(".;")) for item in items]
    return [f"- {item}{'.' if n == len(cleaned) else ';'}" for n, item in enumerate(cleaned, 1)]


def _lower_first(text: str) -> str:
    """Строчная первая буква, если первое слово обычное: «В», «По» – да, «ФИО», «API», «R1» – нет."""
    word = text.split(" ", 1)[0].rstrip(",:;.!?»")
    if word.isalpha() and word[0].isupper() and (len(word) == 1 or word[1:].islower()):
        return text[0].lower() + text[1:]
    return text
