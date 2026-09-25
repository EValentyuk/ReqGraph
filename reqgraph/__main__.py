"""Запуск из командной строки.

python -m reqgraph examples/referral/request.txt
python -m reqgraph examples/referral/request.txt --model openai:gpt-4o-mini
python -m reqgraph --mermaid
"""
import argparse
import sys
import uuid
from pathlib import Path

import yaml
from langgraph.types import Command

from .graph import build_graph, make_checkpointer
from .kb import KnowledgeBase
from .scripted import ScriptedChatModel, load_scripted

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="reqgraph", description="Из сырого запроса заказчика – требования и задачи.")
    parser.add_argument("request", nargs="?", type=Path, help="файл с запросом заказчика")
    parser.add_argument(
        "--model",
        default="scripted",
        help="scripted – сценарная заглушка без ключа; иначе провайдер:модель для init_chat_model, например openai:gpt-4o-mini",
    )
    parser.add_argument("--answers", type=Path, help="YAML со списком ответов заказчика; без него вопросы задаются в консоли")
    parser.add_argument("--kb", type=Path, default=ROOT / "kb", help="папка базы знаний")
    parser.add_argument("--out", type=Path, help="куда записать итоговый документ")
    parser.add_argument("--max-attempts", type=int, default=4, help="сколько раз модель дорабатывает требования и задачи")
    parser.add_argument("--mermaid", action="store_true", help="напечатать схему графа и выйти")
    args = parser.parse_args(argv)

    kb = KnowledgeBase.load(args.kb)
    if args.mermaid:
        print(build_graph(ScriptedChatModel(), kb).get_graph().draw_mermaid())
        return 0
    if args.request is None:
        parser.error("нужен файл с запросом заказчика")

    if args.model == "scripted":
        model = load_scripted(args.request.parent / "script.yaml")
        answers_path = args.answers or args.request.parent / "answers.yaml"
    else:
        from langchain.chat_models import init_chat_model

        model = init_chat_model(args.model, temperature=0)
        answers_path = args.answers
    preset = iter(yaml.safe_load(answers_path.read_text(encoding="utf-8"))) if answers_path and answers_path.exists() else None

    graph = build_graph(model, kb, checkpointer=make_checkpointer(), max_attempts=args.max_attempts)
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    payload = {"request": args.request.read_text(encoding="utf-8").strip(), "dialog": [], "log": []}
    while True:
        pending = None
        for chunk in graph.stream(payload, config, stream_mode="updates"):
            for node, update in chunk.items():
                if node == "__interrupt__":
                    pending = update[0].value
                    continue
                for line in (update or {}).get("log", []):
                    print(f"  {line}")
        if pending is None:
            break
        print("\nВопросы заказчику:")
        answers = []
        for n, question in enumerate(pending["questions"], 1):
            if preset is not None:
                answer = next(preset, "")
                print(f"  {n}. {question}\n     → {answer}")
            else:
                answer = input(f"  {n}. {question}\n     → ").strip()
            answers.append(answer)
        print()
        payload = Command(resume=answers)

    state = graph.get_state(config).values
    out = args.out or ROOT / "out" / f"{args.request.stem}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(state["document"], encoding="utf-8")
    print(f"\nДокумент: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
