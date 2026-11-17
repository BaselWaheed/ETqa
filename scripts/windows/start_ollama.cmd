@echo off
rem Starts Ollama with ETqa's settings (architecture doc, section 5). Values are starting points for Phase 0.
set OLLAMA_HOST=127.0.0.1:11434
set OLLAMA_NUM_PARALLEL=1
set OLLAMA_MAX_LOADED_MODELS=3
set OLLAMA_MAX_QUEUE=16
set OLLAMA_KEEP_ALIVE=5m
rem If the Ollama tray app is running it already listens on 11434: quit it from the tray first.
ollama serve
