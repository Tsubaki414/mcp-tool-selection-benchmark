# MCP Tool Selection Benchmark

Empirical benchmark measuring how LLMs select tools from MCP (Model Context Protocol) tool pools.

## Key Findings

- **Cross-model divergence**: Claude and GPT-4o show dramatically different tool selection behavior (6/10 clusters differ by >25%)
- **Schema compatibility issues**: Some tool schemas work on Claude but fail validation on GPT-4o
- **Selection consistency varies by task complexity**: Tier 1 (explicit) tasks show high consistency; Tier 3 (implicit) tasks show significant variance

## The Problem

When you expose 50+ MCP tools to an LLM, which one does it pick? And does it pick the *right* one?

Current MCP tooling assumes tool selection "just works." This benchmark measures:
1. **Selection rate**: Does the model call any tool at all?
2. **Correct selection**: Does it pick the intended tool?
3. **Cross-model consistency**: Do Claude and GPT-4o agree?

## Schema Compatibility Discovery

During testing, we discovered that **the same tool schema can work on Claude but fail on GPT-4o**:

```python
# This schema passes Claude, fails GPT-4o
{
    "networks": {
        "type": "array",  # ❌ Missing "items" property
        "description": "Networks to check"
    }
}
```

Claude accepts loose schemas; GPT-4o strictly validates. See `demo_schema_compatibility.py`.

## Quick Start

```bash
# Install dependencies
pip install anthropic openai pyyaml

# Set API keys
export ANTHROPIC_API_KEY=your_key
export OPENAI_API_KEY=your_key

# Run the demo
python demo_schema_compatibility.py

# Run full benchmark (Claude)
python src/runner.py --runs 10

# Run cross-model comparison
python src/multi_model_runner.py --model gpt4o --runs 10
```

## Repository Structure

```
├── data/
│   ├── tools.json       # 52 MCP tool definitions (DeFi-focused)
│   ├── tasks.yaml       # 51 test tasks across 3 tiers
│   └── variants.json    # Tool description variants for A/B testing
├── src/
│   ├── runner.py              # Claude benchmark runner
│   ├── multi_model_runner.py  # Cross-model comparison
│   └── analyzer.py            # Results analysis
├── demo_schema_compatibility.py  # Minimal repro of schema issue
└── reports/                      # Generated analysis reports
```

## Methodology

### Task Tiers
- **Tier 1 (Explicit)**: Direct tool name mention ("Use uniswap_swap to...")
- **Tier 2 (Implicit)**: Clear intent without naming ("Swap ETH for USDC")
- **Tier 3 (Ambiguous)**: Underspecified requests ("Check my portfolio")

### Tool Clusters
10 functional clusters: `dex_swap`, `lending`, `portfolio`, `bridge`, `notification`, `calendar`, `data_query`, `nft`, `governance`, `web_fetch`

### Detection
Dual detection: explicit `tool_use` API calls + mentioned tool names in response text.

## Results Summary

| Metric | Claude | GPT-4o |
|--------|--------|--------|
| Overall selection rate | 87% | 62% |
| T1 accuracy | 98% | 95% |
| T3 accuracy | 71% | 43% |
| Schema failures | 0 | 2 clusters |

## License

MIT

## Citation

If you use this benchmark, please cite:
```
MCP Tool Selection Benchmark (2026)
https://github.com/Tsubaki414/mcp-tool-selection-benchmark
```
