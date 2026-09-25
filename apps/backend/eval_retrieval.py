"""Eval de retrieval del RAG: MRR y hit@8 sobre eval_questions.json.

Uso: .venv/bin/python eval_retrieval.py [--k 8]
Solo mide retrieval (sin gastar LLM): para cada pregunta, rank del primer
documento esperado dentro del top-k.
"""

import json
import sys

sys.path.insert(0, ".")

from app.services import rag, store

K = int(sys.argv[sys.argv.index("--k") + 1]) if "--k" in sys.argv else 8


def main() -> None:
    store.store.load()
    with open("eval_questions.json", encoding="utf-8") as f:
        casos = json.load(f)
    mrr, hits, fallos = 0.0, 0, []
    for c in casos:
        # pasa por rag._retrieve: el antes/después se mide solo al mejorarla
        res = rag._retrieve(c["q"], K)
        rank = next(
            (
                i + 1
                for i, r in enumerate(res)
                if any(e.lower() in r["doc_name"].lower() for e in c["docs"])
            ),
            None,
        )
        if rank:
            mrr += 1.0 / rank
            hits += 1
        else:
            fallos.append(c["q"])
        print(f"rank {rank!s:>4} | {c['q'][:65]}")
    n = len(casos)
    print(f"\nMRR@{K} = {mrr / n:.3f} | hit@{K} = {hits}/{n}")
    if fallos:
        print("fallos:")
        for f in fallos:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
