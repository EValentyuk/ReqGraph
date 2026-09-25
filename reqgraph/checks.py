"""Проверки кодом, а не промптом.

Модель охотно дописывает правдоподобные требования, которых никто не просил, и пишет
«быстро» вместо числа. Просьба в промпте этого не отменяет, поэтому всё, что можно
проверить без модели, проверяется здесь – одинаково на каждом прогоне.
"""
import re

from .kb import words
from .models import Issue, Requirement, Task

VAGUE_STEMS = (
    "быстр", "удобн", "корректн", "оптимальн", "надежн",
    "интуитивн", "своевременн", "эффективн", "понятн", "гибк",
)
VAGUE_PHRASES = ("по возможности", "при необходимости", "и т д", "и т п")


def normalize(text: str) -> str:
    """Нижний регистр, ё как е, без пунктуации – чтобы цитата не ломалась на запятой."""
    return " ".join(words(text))


def natural_key(ref: str) -> list:
    """R2 раньше R10."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", ref)]


def check_sources(
    requirements: list[Requirement], request: str, answers: list[str], context_ids: list[str]
) -> list[Issue]:
    """Нет источника – нет требования.

    Цитата обязана найтись дословно в запросе или в ответах заказчика,
    ссылка на базу знаний – среди фрагментов, которые граф действительно нашёл.
    """
    corpus = f" {normalize(' '.join([request, *answers]))} "
    known = set(context_ids)
    issues = []
    for req in requirements:
        source = req.source.strip()
        if source.upper().startswith("KB:"):
            ref = source[3:].strip()
            if ref not in known:
                issues.append(Issue(kind="no_source", ref=req.id, detail=f"фрагмента {ref} нет среди найденных в базе знаний"))
            continue
        quote = normalize(source)
        if not quote or f" {quote} " not in corpus:
            issues.append(Issue(kind="no_source", ref=req.id, detail=f"цитаты «{source}» нет ни в запросе, ни в ответах заказчика"))
    return issues


def check_wording(requirements: list[Requirement]) -> list[Issue]:
    """Слова, которые нельзя проверить на приёмке."""
    issues = []
    for req in requirements:
        tokens = words(req.text)
        padded = f" {' '.join(tokens)} "
        found = [stem for stem in VAGUE_STEMS if any(t.startswith(stem) for t in tokens)]
        found += [phrase for phrase in VAGUE_PHRASES if f" {phrase} " in padded]
        if found:
            issues.append(
                Issue(
                    kind="vague",
                    ref=req.id,
                    detail=f"непроверяемая формулировка: {', '.join(found)} – нужен измеримый критерий или вопрос заказчику",
                )
            )
    return issues


def check_coverage(requirements: list[Requirement], tasks: list[Task]) -> list[Issue]:
    """Каждое требование закрыто задачей, каждая задача опирается на существующие требования."""
    ids = {req.id for req in requirements}
    covered = {ref for task in tasks for ref in task.covers}
    issues = [
        Issue(kind="uncovered", ref=ref, detail="требование не закрыто ни одной задачей")
        for ref in sorted(ids - covered, key=natural_key)
    ]
    for task in tasks:
        if not task.covers:
            issues.append(Issue(kind="orphan", ref=task.id, detail="задача не опирается ни на одно требование"))
        unknown = [ref for ref in task.covers if ref not in ids]
        if unknown:
            issues.append(
                Issue(kind="unknown_ref", ref=task.id, detail=f"ссылается на несуществующие требования: {', '.join(unknown)}")
            )
    return issues
