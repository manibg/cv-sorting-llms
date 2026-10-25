# Capstone_Project-CS[02] — CV Sorting using LLMs

## Documentation

- [Overview — summary, features, LLMs, NFRs](docs/overview.md)
- [Technical guide — steps & architecture](docs/technical-guide.md)

---

Rank candidate CVs against a job description using two free local Ollama models: **llama3.2** + **gemma2**.

## Layout

```
Capstone_Project-CS[02]/
├── Codebase/          # runnable Python package (flat, ./ -friendly)
│   ├── main.py        # required entrypoint
│   ├── execution.txt  # how to run
│   ├── config.py / parsers.py / prompts.py / llm_client.py / matcher.py / ranker.py
│   ├── test_*.py      # edge-case unit tests
│   └── sample_data/   # demo JD + CVs
├── docs/              # project overview + technical guide
└── Report/
    └── Report.pdf     # ≤3 page report
```

## Accepted input files

| Input | Formats | Notes |
|-------|---------|--------|
| **Candidate CVs** | `.txt`, `.pdf`, `.docx` | One or many; formats can be mixed |
| **Job description** | `.txt`, `.pdf`, `.docx` **or pasted text** | Exactly one JD per run |

Optional: required-skills filter, model selection (`llama3.2` / `gemma2`), mock mode.

## Quick start

```bash
cd Codebase
pip install -r requirements.txt

# Install Ollama from https://ollama.com then:
ollama pull llama3.2
ollama pull gemma2

python main.py --cvs ./sample_data/cvs --jd ./sample_data/job_description.txt

# Offline demo / CI
python main.py --cvs ./sample_data/cvs --jd ./sample_data/job_description.txt --mock

# Demo UI
python ui_server.py
# → http://127.0.0.1:7860

# Tests
python -m unittest discover -s . -p 'test_*.py' -v
```

## Plug-and-play

- Swap models with `--models llama3.2,gemma2`
- Swap backend by implementing `LLMProvider` in `llm_client.py` (factory: `create_provider`)
- No LangChain — plain Python + Ollama HTTP API
