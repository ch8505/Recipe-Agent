# ChefScout: one agent, two harnesses

A personal cooking agent (recipes, online search on TheMealDB, shopping list, memory across sessions), built twice:

- `API/`: on the raw Messages API, with a hand-written harness (`API/harness/{loop,tools,history,memory,context,compaction,caching,tokens}.py`)
- `SDK/`: on the Claude Agent SDK (lines marked `# replaces: <part>`)
- `shared/`: domain code and data used by both
- `tests/`: offline tests with a fake client (no key needed)
- `scenario.json`, `results/`, `REPORT.md` (Hebrew): the measurement and the comparison

```powershell
pip install -r requirements.txt
python -m pytest -q
$env:ANTHROPIC_API_KEY = "sk-ant-..."    # API version only; never commit a key
python API/main.py --scenario scenario.json --out results/api.json
Remove-Item Env:ANTHROPIC_API_KEY
python SDK/main.py --scenario scenario.json --out results/sdk.json
python compare.py
```
