# MCP Tool Selection Benchmark

Empirical benchmark measuring how LLMs select tools from MCP (Model Context Protocol) tool pools.

## Key Findings

| Metric | Claude Sonnet 4.6 | GPT-4o | Gap |
|--------|-------------------|--------|-----|
| **Overall (V4, 673 tools)** | 72.2% | 52.0% | +20.2pp |
| **Overall (V1, 52 tools)** | 64.7% | 40.9% | +23.8pp |
| **T1 Direct** | 79.4% | 71.1% | +8.3pp |
| **T2 Ambiguous** | 57.2% | 40.0% | +17.2pp |
| **T3 Competitive** | 80.0% | 45.0% | +35.0pp |

## Three Failure Modes

1. **Schema Failure**: Agent recognizes tool but cannot complete the call
2. **Description Failure**: Agent doesn't connect task to tool
3. **Compatibility Failure**: Tool works on Claude but fails validation on GPT-4o

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

# Run the schema compatibility demo
python demo_schema_compatibility.py

# Run full benchmark (V4)
python src/benchmark_v4.py
```

## Repository Structure

```
├── data/
│   ├── tools.json         # V1: 52 curated MCP tools
│   ├── tools_v4.json      # V4: 673 tools from awesome-mcp-servers
│   ├── tasks.yaml         # V1: 51 test tasks
│   └── tasks_v4.yaml      # V4: 90 test tasks (15 clusters × 6)
├── src/
│   ├── runner.py                # V1 Claude benchmark
│   ├── multi_model_runner.py    # Cross-model comparison
│   ├── benchmark_v4.py          # V4 parallel benchmark runner
│   └── generate_report.py       # Report generator
├── docs/
│   └── METHODOLOGY_V4.md        # Full methodology documentation
├── reports/
│   └── FULL_REPORT.html         # Complete analysis report
└── demo_schema_compatibility.py # Schema issue demo
```

## Benchmark Versions

### V1 (52 Tools)
- **Source**: Manually curated from major MCP repositories
- **Runs**: 1,629 (Claude 1,204 + GPT-4o 425)
- **Focus**: DeFi, productivity tools
- **Key finding**: Schema Compatibility Failure

### V4 (673 Tools)
- **Source**: Crawled from [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
- **Runs**: 1,080 (540 per model)
- **Clusters**: 15 functional categories
- **Key finding**: Patterns persist at scale

## Methodology

### Task Tiers
- **T1 (Direct)**: Explicitly names the tool — "Use uniswap_swap to..."
- **T2 (Ambiguous)**: Clear intent without naming — "Swap ETH for USDC"
- **T3 (Competitive)**: Vague or multi-tool applicable — "Check my portfolio"

### Detection
- Primary: `tool_use` stop reason (explicit API call)
- Secondary: Fuzzy name matching in response text

### Configuration
- Temperature: 0 (deterministic)
- Runs per task: 10
- Tool pool: Shuffled per run

## Results Summary

### By Cluster (V4)

| Cluster | Claude | GPT-4o | Gap |
|---------|--------|--------|-----|
| bridging | 100% | 86.7% | +13.3pp |
| cloud_infra | 95.0% | 86.7% | +8.3pp |
| database | 86.7% | 51.7% | +35.0pp |
| docs_productivity | 81.7% | 48.3% | +33.4pp |
| notification | 70.0% | 41.7% | +28.3pp |

## License

MIT

## Citation

```
MCP Tool Selection Benchmark (2026)
https://github.com/Tsubaki414/mcp-tool-selection-benchmark
```
