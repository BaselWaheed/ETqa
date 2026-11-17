# Phase 0: environment spike

These scripts answer the uncertainties U1, U2, U5, U6, U7, U8, U11 and U13 (architecture doc, section 8) on
the real Windows machine. Results land in `phase0_report/` as JSON. Only `pdf_arabic_check.py` needs a
package (`pip install --user pypdf`); everything else is standard-library Python.

Run them as a **standard user** with other heavy applications closed.

| Step | Command | Answers |
| --- | --- | --- |
| 1 | `python scripts/phase0/env_check.py --pg postgres://USER:PASS@127.0.0.1:5432/etqa` | U11 |
| 2 | `python scripts/phase0/bench_ollama.py generate` | U1, U2 (main model) |
| 3 | `python scripts/phase0/bench_ollama.py generate --threads <physical cores>` | thread setting |
| 4 | `python scripts/phase0/bench_ollama.py generate --model qwen2.5:1.5b-instruct-q4_K_M --contexts 2048` | SLM speed |
| 5 | `python scripts/phase0/bench_ollama.py embed` | U7 |
| 6 | `python scripts/phase0/bench_ollama.py structured --n 200` | U8 |
| 7 | `python scripts/phase0/bench_ollama.py cancel` | U13 |
| 8 | `python scripts/phase0/bench_ollama.py vision --image <a real diagram>` | ADR-09 |
| 9 | `python scripts/phase0/pdf_arabic_check.py <folder of 10 Arabic/mixed PDFs>` | U5 |
| 10 | `python scripts/phase0/ocr_check.py <folder of 20 scanned pages + .txt ground truth>` | U6 |

For U2 (peak memory), keep Task Manager's Performance tab open during step 2 and note the highest
"In use" value; the script records available memory before and after loading as a cross-check.

Use fake or non-sensitive sample documents if the report will be shared outside the team.
Fill in `documentation/phase0-report-template.md` from the JSON files.
