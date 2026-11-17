# Phase 0 benchmark report

Machine: (CPU model, physical cores, RAM)  ·  Date:  ·  Run by:

| # | Question | Result (from phase0_report/*.json) | Decision |
| --- | --- | --- | --- |
| U1 | 7B speed: first-token time and tokens/s at 2k / 4k / 8k context | | Go / no-go on Qwen2.5 7B |
| U2 | Peak RAM with LLM + BGE-M3 + SLM loaded | | `OLLAMA_MAX_LOADED_MODELS` value |
| U5 | pypdf Arabic order on 10 real PDFs | | Keep pypdf / evaluate alternative |
| U6 | Tesseract CER on 20 scanned pages | | OCR settings, review threshold |
| U7 | BGE-M3 dims (expect 1024), chunks/s by batch size | | Embedding batch size |
| U8 | SLM valid JSON and correct labels out of 200 | | SLM routing vs rules only |
| U11 | Everything installed and found as a standard user | | Setup guide changes |
| U13 | Does closing the stream stop generation? | | Cancel wording (already "stop waiting") |
| ADR-09 | Qwen3-VL 4B: loads alone, description quality on 5 real diagrams | | Keep / replace |

**First-token latency target N for Phase 5:** (set from U1 at the context size chunk retrieval will use)
