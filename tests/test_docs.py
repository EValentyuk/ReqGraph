import re
from pathlib import Path

from reqgraph import KnowledgeBase, build_graph
from reqgraph.scripted import ScriptedChatModel

ROOT = Path(__file__).resolve().parent.parent
EDGE = re.compile(r"^\s*(\w+)\s*-->(?:\|[^|]*\|)?\s*(\w+)\s*$")
ALIASES = {"__start__": "begin", "__end__": "done"}


def test_diagram_matches_graph():
    """Схема в README не отстаёт от кода: рёбра на картинке – ровно рёбра графа."""
    source = (ROOT / "docs" / "diagrams" / "src" / "graph.mmd").read_text(encoding="utf-8")
    drawn = {match.groups() for line in source.splitlines() if (match := EDGE.match(line))}
    graph = build_graph(ScriptedChatModel(), KnowledgeBase.load(ROOT / "kb")).get_graph()
    real = {(ALIASES.get(e.source, e.source), ALIASES.get(e.target, e.target)) for e in graph.edges}
    assert drawn == real
