"""Phase 5 evaluation: retrieval and answer quality on a fixed question set (architecture doc, section 7).

Input: JSON Lines, one question per line, e.g.
{"id": "q001", "question": "...", "category": "en", "expected_documents": ["Billing guide"],
 "expected_locators": ["p. 3"], "should_be_insufficient": false}
category is one of: ar, en, mixed, identifier, cross-lingual.

Usage:
  python manage.py evaluate_rag documentation/eval/questions.jsonl --user evaluator             (retrieval only)
  python manage.py evaluate_rag documentation/eval/questions.jsonl --user evaluator --answers   (full answers)
Writes a JSON report next to the input file unless --out is given. Never counts a run with errors as passing.
"""
import json
import pathlib
import statistics
import time
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.access.scope import build_scope
from apps.ai.models import AIExecution
from apps.chat.handlers import answer_question
from apps.chat.services import answer_language
from apps.retrieval.services import search


class Command(BaseCommand):
    help = __doc__.splitlines()[0]

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--user", required=True, help="Evaluate with this user's access scope.")
        parser.add_argument("--answers", action="store_true", help="Also generate answers (slow on CPU).")
        parser.add_argument("--k", type=int, default=8)
        parser.add_argument("--out", default="")

    def handle(self, *args, file, user, answers, k, out, **options):
        path = pathlib.Path(file)
        if not path.exists():
            raise CommandError(f"{path} not found")
        try:
            evaluator = get_user_model().objects.get(username=user)
        except get_user_model().DoesNotExist as exc:
            raise CommandError(f"user {user!r} not found") from exc
        items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        scope = build_scope(evaluator)
        rows = []
        for item in items:
            row = {"id": item.get("id"), "category": item.get("category", "en")}
            expected = {d.lower() for d in item.get("expected_documents", [])}
            started = time.perf_counter()
            result = search(item["question"], scope, k=k)
            row["retrieval_ms"] = int((time.perf_counter() - started) * 1000)
            titles = [p.document_title.lower() for p in result.passages]
            rank = next((i for i, t in enumerate(titles, 1) if t in expected), None)
            row.update(hit=rank is not None if expected else None, reciprocal_rank=(1 / rank) if rank else 0.0,
                       retrieved=len(titles), vector_used=result.vector_used)
            if answers:
                lang = answer_language(item["question"])
                last_exec = AIExecution.objects.order_by("-id").values_list("id", flat=True).first() or 0
                started = time.perf_counter()
                try:
                    out_ = answer_question(evaluator, item["question"], lang)
                    row["answer_ms"] = int((time.perf_counter() - started) * 1000)
                    cited = {c["title"].lower() for c in out_["citations"]}
                    row.update(evidence=out_["evidence"],
                               citation_correct=bool(cited) and cited <= expected if expected else None,
                               insufficient_correct=(out_["evidence"] == "insufficient") == bool(item.get("should_be_insufficient")))
                    first = AIExecution.objects.filter(id__gt=last_exec, task="chat.answer", outcome="ok") \
                        .values_list("first_token_ms", flat=True).first()
                    row["first_token_ms"] = first
                except Exception as exc:  # noqa: BLE001 - recorded as an error, never as a pass
                    row.update(error=f"{exc.__class__.__name__}: {exc}"[:300])
            rows.append(row)
            self.stdout.write(f"{row['id']}: hit={row['hit']} rr={row['reciprocal_rank']:.2f} "
                              f"{'evidence=' + str(row.get('evidence')) if answers else ''}")
        report = self.summarize(rows, answers)
        report["questions"] = rows
        report["user"] = user
        target = pathlib.Path(out) if out else path.with_suffix(".report.json")
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        self.stdout.write(json.dumps({k: v for k, v in report.items() if k != "questions"}, indent=2, ensure_ascii=False))
        self.stdout.write(f"Report written to {target}")

    @staticmethod
    def summarize(rows, answers) -> dict:
        def block(subset):
            scored = [r for r in subset if r["hit"] is not None]
            out = {"questions": len(subset),
                   "hit_rate": round(sum(r["hit"] for r in scored) / len(scored), 3) if scored else None,
                   "mrr": round(statistics.mean(r["reciprocal_rank"] for r in scored), 3) if scored else None,
                   "median_retrieval_ms": statistics.median(r["retrieval_ms"] for r in subset) if subset else None}
            if answers:
                done = [r for r in subset if "error" not in r]
                cites = [r["citation_correct"] for r in done if r.get("citation_correct") is not None]
                firsts = [r["first_token_ms"] for r in done if r.get("first_token_ms")]
                out.update(errors=len(subset) - len(done),
                           citation_correctness=round(sum(cites) / len(cites), 3) if cites else None,
                           insufficient_correctness=round(sum(r["insufficient_correct"] for r in done) / len(done), 3) if done else None,
                           unsupported_answers=sum(1 for r in done if r.get("evidence") == "unsupported"),
                           median_first_token_ms=statistics.median(firsts) if firsts else None)
            return out
        by_cat = defaultdict(list)
        for r in rows:
            by_cat[r["category"]].append(r)
        return {"overall": block(rows), "by_category": {c: block(rs) for c, rs in sorted(by_cat.items())}}
