from pathlib import Path

import yaml
from langgraph.types import Command, RetryPolicy

from reqgraph import KnowledgeBase, build_graph, make_checkpointer
from reqgraph.graph import retry_on
from reqgraph.scripted import ScriptedChatModel, load_scripted

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "referral"
KB = KnowledgeBase.load(ROOT / "kb")
FAST_RETRY = RetryPolicy(max_attempts=2, initial_interval=0.01, jitter=False, retry_on=retry_on)


def run(graph, request: str, resumes: list):
    """Прогон до конца: на каждом interrupt отдаём следующий набор ответов."""
    config = {"configurable": {"thread_id": "test"}}
    result = graph.invoke({"request": request, "dialog": [], "log": []}, config)
    interrupts = []
    while "__interrupt__" in result:
        interrupts.append(result["__interrupt__"][0].value)
        result = graph.invoke(Command(resume=resumes.pop(0)), config)
    return result, interrupts


def test_referral_scenario_end_to_end():
    model = load_scripted(EXAMPLE / "script.yaml")
    graph = build_graph(model, KB, checkpointer=make_checkpointer())
    answers = yaml.safe_load((EXAMPLE / "answers.yaml").read_text(encoding="utf-8"))

    result, interrupts = run(graph, (EXAMPLE / "request.txt").read_text(encoding="utf-8"), [answers])

    assert len(interrupts) == 1 and len(interrupts[0]["questions"]) == 3
    assert model.calls == ["Extraction"] * 3 + ["Decomposition"] * 2
    assert result["attempts"] == 3 and result["decompose_attempts"] == 2
    assert result["issues"] == [] and result["coverage_issues"] == []

    log = "\n".join(result["log"])
    assert "check_sources: без источника – R4" in log  # выдуманные 1000 рублей пойманы кодом
    assert "check_wording: непроверяемые формулировки – R3" in log  # «быстро» тоже
    assert "check_coverage: без задачи – R5, R8" in log  # забытые задачи
    assert "новые: glossary.device" in log  # ответ заказчика расширил контекст

    assert not any("1000" in r.text for r in result["requirements"])
    for r in result["requirements"]:
        assert f"| {r.id} |" in result["document"]
    assert "## Не закрыто" not in result["document"]


def test_open_issues_reach_document_when_attempts_run_out():
    bad = {"requirements": [{"id": "R1", "text": "Система должна работать быстро.", "kind": "nonfunctional", "source": "быстро"}]}
    model = ScriptedChatModel(responses={"Extraction": [bad, dict(bad)]})
    graph = build_graph(model, KB, checkpointer=make_checkpointer(), max_attempts=2)

    result, _ = run(graph, "Нужно, чтобы работало быстро.", [])

    assert model.calls == ["Extraction", "Extraction"]
    assert "tasks" not in result
    document = result["document"]
    assert "## Не закрыто" in document and "R1: непроверяемая формулировка" in document


def test_broken_model_output_is_retried():
    broken = {"requirements": [{"id": "R1"}]}
    good = {
        "requirements": [
            {"id": "R1", "text": "Клиент может скачать выписку в PDF.", "kind": "functional", "source": "скачать выписку в PDF"}
        ]
    }
    plan = {"epic": "Выписка", "tasks": [{"id": "T1", "title": "Кнопка выписки", "covers": ["R1"], "acceptance": ["Файл формируется"]}]}
    model = ScriptedChatModel(responses={"Extraction": [broken, good], "Decomposition": [plan]})
    graph = build_graph(model, KB, checkpointer=make_checkpointer(), retry_policy=FAST_RETRY)

    result, _ = run(graph, "Хочу скачать выписку в PDF.", [])

    assert model.calls == ["Extraction", "Extraction", "Decomposition"]
    assert result["attempts"] == 1  # повтор после сбоя разбора – не попытка доработки


def test_graph_shape():
    mermaid = build_graph(ScriptedChatModel(), KB).get_graph().draw_mermaid()
    for node in ("retrieve", "extract", "check_sources", "check_wording", "review", "ask_human", "decompose", "check_coverage", "render"):
        assert node in mermaid
