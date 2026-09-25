from pathlib import Path

from reqgraph.checks import check_coverage, check_sources, check_wording
from reqgraph.kb import KnowledgeBase
from reqgraph.models import Requirement, Task

ROOT = Path(__file__).resolve().parent.parent


def req(rid: str, text: str, source: str, kind: str = "functional") -> Requirement:
    return Requirement(id=rid, text=text, kind=kind, source=source)


def test_quote_survives_punctuation_case_and_yo():
    reqs = [req("R1", "Система должна начислить бонус.", "Когда друг оформит карту обоим начисляется бонус")]
    request = "…и когда друг оформит карту, обоим начисляется бонус. Всё должно работать."
    assert check_sources(reqs, request, [], []) == []


def test_invented_value_has_no_source():
    reqs = [req("R4", "Бонус – 1000 рублей.", "бонус 1000 рублей")]
    issues = check_sources(reqs, "Обоим начисляется бонус.", [], [])
    assert [(i.kind, i.ref) for i in issues] == [("no_source", "R4")]


def test_quote_from_customer_answer_counts():
    reqs = [req("R3", "Бонус поступает не позже 24 часов.", "не позже суток")]
    assert check_sources(reqs, "Обоим начисляется бонус.", ["Не позже суток после выпуска карты."], []) == []


def test_kb_reference_must_be_found_by_retrieval():
    reqs = [req("R6", "Повтор не задваивает начисление.", "KB:nfr.idempotency", "nonfunctional")]
    assert check_sources(reqs, "запрос", [], ["nfr.idempotency"]) == []
    assert check_sources(reqs, "запрос", [], ["nfr.audit"])[0].kind == "no_source"


def test_part_of_word_is_not_a_quote():
    reqs = [req("R1", "Текст.", "онус")]
    assert check_sources(reqs, "Обоим начисляется бонус.", [], [])[0].ref == "R1"


def test_vague_wording_flagged_and_measurable_passes():
    reqs = [
        req("R1", "Начисление должно происходить быстро и по возможности надёжно.", "x", "nonfunctional"),
        req("R2", "Бонус поступает не позже 24 часов после выпуска карты.", "x", "nonfunctional"),
    ]
    issues = check_wording(reqs)
    assert [i.ref for i in issues] == ["R1"]
    assert "быстр" in issues[0].detail and "надежн" in issues[0].detail and "по возможности" in issues[0].detail


def test_coverage_finds_gaps_orphans_and_broken_refs():
    reqs = [req("R1", "a", "a"), req("R2", "b", "b"), req("R10", "c", "c")]
    tasks = [
        Task(id="T1", title="t", covers=["R1", "R9"], acceptance=["x"]),
        Task(id="T2", title="t", covers=[], acceptance=["x"]),
    ]
    issues = check_coverage(reqs, tasks)
    assert [(i.kind, i.ref) for i in issues] == [
        ("uncovered", "R2"),
        ("uncovered", "R10"),
        ("unknown_ref", "T1"),
        ("orphan", "T2"),
    ]


def test_retrieval_is_explainable_and_selective():
    kb = KnowledgeBase.load(ROOT / "kb")
    found = {f["id"]: f["matched"] for f in kb.retrieve("Клиент делится ссылкой с другом, обоим начисляется бонус.")}
    assert found["glossary.bonus"] == ["бонус"]
    assert "system.credit" not in found and "glossary.device" not in found
    assert "glossary.device" in {f["id"] for f in kb.retrieve("совпадает телефон или устройство")}
