"""Excel export in the template's exact column order (openpyxl)."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .models import TCSet
from .validation import case_problems

HEADER_FILL = PatternFill("solid", fgColor="E00800")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")


class ExportBlocked(Exception):
    def __init__(self, problems: dict[int, list[str]]):
        super().__init__("Some test cases fail validation.")
        self.problems = problems


def _cell_value(tc, key: str) -> str:
    if key == "steps":
        return "\n".join(f"{i}. {s['action']}" for i, s in enumerate(tc.steps, 1))
    if key == "expected_result":
        per_step = "\n".join(f"{i}. {s['expected']}" for i, s in enumerate(tc.steps, 1))
        overall = tc.fields.get("expected_result", "")
        return f"{per_step}\nOverall: {overall}" if per_step else overall
    return tc.fields.get(key, "")


def validate_for_export(tc_set: TCSet) -> dict[int, list[str]]:
    problems = {}
    for tc in tc_set.cases.all():
        issues = case_problems({**tc.fields, "steps": tc.steps})
        if issues:
            problems[tc.ordinal] = issues
    return problems


def to_xlsx(tc_set: TCSet) -> bytes:
    problems = validate_for_export(tc_set)
    if problems:
        raise ExportBlocked(problems)
    columns = tc_set.template.columns
    wb = Workbook()
    ws = wb.active
    ws.title = "Test Cases"
    ws.append([c["label"] for c in columns])
    for tc in tc_set.cases.prefetch_related("sources"):
        ws.append([_cell_value(tc, c["key"]) for c in columns])
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP
    widths = {"name": 40, "objective": 45, "preconditions": 35, "steps": 60, "expected_result": 60, "test_data": 30,
              "folder": 30}
    for i, col in enumerate(columns, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = widths.get(col["key"], 16)
    ws.freeze_panes = "B2"

    src = wb.create_sheet("Sources")
    src.append(["Test case", "Scenario type", "Assumption", "Document", "Version", "Location", "Section"])
    for tc in tc_set.cases.prefetch_related("sources"):
        sources = list(tc.sources.all())
        if not sources:
            src.append([tc.fields.get("name", ""), tc.scenario_type, "yes", "", "", "", ""])
        for s in sources:
            src.append([tc.fields.get("name", ""), tc.scenario_type, "yes" if tc.assumption else "no", s.title,
                        s.version_no, s.locator, s.section_path])
    for cell in src[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
