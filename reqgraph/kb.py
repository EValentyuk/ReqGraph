"""Машиночитаемая база знаний: глоссарий, системы, типовые нефункциональные требования.

Каждая запись – YAML с полем keys: основы слов, по которым запись находится в тексте.
Поиск детерминированный и объяснимый – видно, по какому слову нашёлся фрагмент.
Эмбеддинги могут его заменить, узел графа от этого не изменится.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

WORD = re.compile(r"[а-яa-z0-9]+")


def words(text: str) -> list[str]:
    """Слова текста: нижний регистр, ё как е, без пунктуации."""
    return WORD.findall(text.lower().replace("ё", "е"))


@dataclass(frozen=True)
class Fragment:
    id: str
    kind: str
    text: str
    keys: tuple[str, ...]


class KnowledgeBase:
    def __init__(self, fragments: list[Fragment]):
        self.fragments = fragments

    @classmethod
    def load(cls, folder: Path) -> "KnowledgeBase":
        fragments = []
        for path in sorted(Path(folder).glob("*.yaml")):
            for item in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
                fragments.append(
                    Fragment(
                        id=item["id"],
                        kind=path.stem,
                        text=_text(path.stem, item),
                        keys=tuple(key.lower().replace("ё", "е") for key in item["keys"]),
                    )
                )
        return cls(fragments)

    def retrieve(self, text: str) -> list[dict]:
        """Фрагменты, чьи ключи встретились в тексте как начало слова."""
        tokens = words(text)
        found = []
        for fragment in self.fragments:
            matched = sorted({key for key in fragment.keys if any(t.startswith(key) for t in tokens)})
            if matched:
                found.append({"id": fragment.id, "kind": fragment.kind, "text": fragment.text, "matched": matched})
        return found


def _text(kind: str, item: dict) -> str:
    if kind == "glossary":
        return f"{item['term']} – {item['definition']}"
    if kind == "systems":
        return f"{item['name']}: {item['what']}"
    return item["text"]
