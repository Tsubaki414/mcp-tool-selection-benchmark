# MCP Tool Selection Benchmark V4
## Methodology & Execution Plan

**Version:** 4.0  
**Date:** 2026-03-13  
**Author:** Snowmaker + Molt

---

## 1. Executive Summary

This benchmark measures how LLMs select tools from large MCP tool pools. We test whether models can:
1. Find the right tool when asked directly (T1)
2. Infer the right tool from ambiguous requests (T2)
3. Choose between competing tools (T3)

**Scale:**
- 673 tools (from 1,529 raw entries)
- 15 functional clusters
- 90 benchmark tasks
- 2 models: Claude Sonnet 4.6, GPT-4o
- ~120,000 total API calls

---

## 2. Data Collection

### 2.1 Source
Tools were collected from **awesome-mcp-servers** (github.com/punkpeye/awesome-mcp-servers), the largest curated list of MCP servers with 83,000+ stars.

**Why this source:**
- Community-curated quality filter
- Real production tools, not demos
- Includes GitHub links for schema verification
- Covers all major use cases

### 2.2 Filtering Process

| Step | Count | Criteria |
|------|-------|----------|
| Raw entries | 1,529 | Parsed from README |
| After skip filter | 1,468 | Removed: awesome-lists, templates, demos, aggregators, proxies |
| After classification | 723 | Kept only tools matching defined clusters |
| After deduplication | 673 | Removed name-similar duplicates |

**Skip patterns:**
```python
SKIP_PATTERNS = [
    'awesome', 'template', 'example', 'demo', 'test', 
    'boilerplate', 'tutorial', 'sample', 'skeleton',
    'aggregator', 'proxy', 'gateway', 'hub', 'registry',
    'orchestrator', 'meta', 'inspector', 'debugger', 'client'
]
```

---

## 3. Classification System

### 3.1 Cluster Definitions

Tools are classified into 15 functional clusters based on keyword matching:

| Cluster | Keywords | Tools |
|---------|----------|-------|
| **ai_ml** | openai, anthropic, huggingface, embedding, vector, rag, llm, arxiv | 117 |
| **database** | sql, postgres, mysql, sqlite, mongodb, redis, clickhouse, bigquery | 94 |
| **bridging** | bridge, cross-chain, layerzero, stargate, wormhole | 71 |
| **calendar** | calendar, gcal, schedule, todoist, linear, task management | 60 |
| **code_tools** | github, gitlab, git repo, pull request, issue, lsp | 50 |
| **cloud_infra** | aws, cloudflare, kubernetes, docker, terraform, azure | 45 |
| **finance_data** | stock, market data, trading, financial, yahoo finance | 41 |
| **web_fetch** | scrape, crawl, firecrawl, playwright, puppeteer | 38 |
| **dex_swap** | swap, dex, uniswap, 1inch, jupiter, sushiswap | 38 |
| **search** | brave search, tavily, exa, serper, google search | 34 |
| **docs_productivity** | notion, obsidian, excel, google sheets, airtable | 33 |
| **notification** | slack, discord, telegram, email, gmail, webhook | 27 |
| **file_ops** | filesystem, read file, write file, directory | 15 |
| **portfolio** | portfolio, debank, zapper, zerion, wallet balance | 6 |
| **lending** | aave, compound, lending, borrow, morpho | 4 |

### 3.2 Classification Algorithm

```python
def classify_tool(tool):
    text = f"{tool['name']} {tool['description']}".lower()
    
    for cluster, rules in CLUSTER_RULES.items():
        # Must contain at least one positive keyword
        if any(keyword in text for keyword in rules['must_have']):
            # Must not contain any negative keywords
            if not any(kw in text for kw in rules['must_not_have']):
                return cluster
    
    return None  # Filtered out
```

**Negative keywords prevent misclassification:**
- `dex_swap` excludes: 'music', 'code', 'assistant'
- `lending` excludes: 'blender', 'code'

---

## 4. Prompt Design

### 4.1 Three-Tier System

| Tier | Name | Description | Example |
|------|------|-------------|---------|
| **T1** | Direct | Explicitly names tool or uses exact terminology | "Swap 100 USDC to ETH on Uniswap V3" |
| **T2** | Ambiguous | Clear intent, no specific tool named | "Exchange my stablecoins for ETH with best rates" |
| **T3** | Competitive | Vague or pits multiple tools against each other | "Find optimal route for a large token swap" |

### 4.2 Prompt Generation Process

Prompts were generated using Claude Sonnet 4.6 with this meta-prompt:

```
You are generating benchmark tasks for testing AI tool selection.

Given this cluster of tools:
{tools_json}

Generate exactly 6 tasks (2 per tier):

**T1 (Direct)**: Explicitly names the tool or uses very specific 
terminology that maps to one tool.

**T2 (Ambiguous)**: Describes the intent clearly but doesn't name 
specific tools. Multiple tools could work.

**T3 (Competitive)**: Pits tools against each other or uses vague 
language that could match multiple tools.

Be realistic. Use actual tool names from the list. 
Make prompts sound like real user requests.
```

### 4.3 Example Prompts by Cluster

**database cluster:**
```yaml
T1: "Query our PostgreSQL database using mcp-server-postgres to get 
    all users who signed up in the last 30 days."
    
T2: "I need to run some analytics queries on our production database 
    without setting up a complex BI tool."
    
T3: "Pull aggregated metrics from our data warehouse — we use a mix 
    of SQL databases and might need to query multiple sources."
```

**notification cluster:**
```yaml
T1: "Send a Slack message to #engineering channel using the 
    korotovsky slack-mcp-server."
    
T2: "Notify the team about the deployment completion — we use 
    multiple chat platforms."
    
T3: "Alert relevant stakeholders when the build fails — could be 
    email, chat, or push notification."
```

---

## 5. Benchmark Execution

### 5.1 Configuration

```python
MODELS = {
    "claude": "claude-sonnet-4-6",
    "gpt4o": "gpt-4o"
}

TEMPERATURE = 0          # Deterministic output
RUNS_PER_TASK = 10       # Statistical significance
MAX_CONCURRENT = 5       # Rate limiting
```

### 5.2 Detection Methods

**Dual detection for robustness:**

1. **tool_use detection**: Check if model returns `stop_reason: tool_use`
2. **mention detection**: Fuzzy match tool names in response text

```python
def detect_selection(response, tool_pool):
    # Method 1: Explicit tool call
    if response.stop_reason == "tool_use":
        return response.tool_calls[0].name, "tool_use"
    
    # Method 2: Tool mentioned in text
    for tool in tool_pool:
        if tool.id.lower() in response.text.lower():
            return tool.id, "mentioned"
    
    return None, "none"
```

### 5.3 Execution Plan

| Phase | Tasks | API Calls | Est. Time | Est. Cost |
|-------|-------|-----------|-----------|-----------|
| Claude run | 90 tasks × 10 runs | 900 | 3-4 hrs | $40-60 |
| GPT-4o run | 90 tasks × 10 runs | 900 | 3-4 hrs | $50-70 |
| **Total** | | ~1,800 | 6-8 hrs | $100-150 |

*Note: Runs are parallelized within rate limits*

---

## 6. Analysis Framework

### 6.1 Primary Metrics

| Metric | Definition |
|--------|------------|
| **Selection Rate** | % of runs where any tool was selected |
| **Accuracy** | % of runs where correct tool was selected |
| **Mention Rate** | % of runs where correct tool was mentioned (even if not called) |
| **Cross-Model Delta** | Difference in selection rate between Claude and GPT-4o |

### 6.2 Failure Mode Classification

| Mode | Signal | Root Cause |
|------|--------|------------|
| **Schema Failure** | High mention, low invoke | Parameter/schema issues |
| **Description Failure** | Low mention, low invoke | Poor semantic signal |
| **Compatibility Failure** | Works on Claude, fails on GPT | Strict schema validation |

### 6.3 Baseline Control

Best-performing tool per cluster serves as "ideal tool" baseline.
- If ideal tool achieves 95%+ → failures are tool-side
- If ideal tool achieves <60% → failures are model-side

---

## 7. Deliverables

1. **Raw data**: SQLite database with all runs
2. **Analysis report**: PDF with findings
3. **Cross-model heatmap**: Selection rates by cluster × model
4. **Failure mode breakdown**: Per-cluster diagnosis
5. **Code repository**: Full benchmark code on GitHub

---

## 8. Timeline

| Date | Milestone |
|------|-----------|
| 2026-03-13 | Data collection & cleaning ✅ |
| 2026-03-13 | Prompt generation ✅ |
| 2026-03-13-14 | Benchmark execution |
| 2026-03-14-15 | Analysis & visualization |
| 2026-03-15-16 | Report writing |
| 2026-03-16+ | Publication |

---

## Appendix A: Cluster Keywords

```python
CLUSTER_RULES = {
    'dex_swap': {
        'must_have': ['swap', 'dex', 'uniswap', '1inch', 'jupiter', 
                      'sushiswap', 'pancakeswap', 'curve', 'balancer'],
        'must_not_have': ['music', 'code', 'assistant']
    },
    'lending': {
        'must_have': ['aave', 'compound', 'lending', 'borrow', 
                      'morpho', 'maker', 'liquity'],
        'must_not_have': ['blender', 'code']
    },
    'portfolio': {
        'must_have': ['portfolio', 'debank', 'zapper', 'zerion', 
                      'wallet balance', 'defi position'],
    },
    'database': {
        'must_have': ['sql', 'postgres', 'mysql', 'sqlite', 'mongodb', 
                      'redis', 'clickhouse', 'bigquery', 'supabase', 
                      'database', 'dynamodb', 'firestore'],
    },
    'search': {
        'must_have': ['brave search', 'tavily', 'exa', 'serper', 
                      'google search', 'bing search', 'duckduckgo', 
                      'perplexity', 'web search'],
        'must_not_have': ['file search', 'code search']
    },
    'notification': {
        'must_have': ['slack', 'discord', 'telegram', 'email', 'gmail', 
                      'sendgrid', 'twilio', 'sms', 'push notification'],
    },
    # ... (full list in code)
}
```

---

## Appendix B: Sample Tasks (First 3 Clusters)

### ai_ml
```yaml
- id: ai_ml_t1_01
  tier: T1
  prompt: "Set up MCPJungle as our self-hosted MCP server registry"
  target_tools: [mcpjungle]

- id: ai_ml_t2_01  
  tier: T2
  prompt: "I want my AI assistant to automatically find and connect 
          to new MCP servers without manual configuration"
  target_tools: [magg, mcpjungle]

- id: ai_ml_t3_01
  tier: T3
  prompt: "Route my agent's queries to the right retrieval services 
          and let it call specialized AI agents for complex tasks"
  target_tools: [ragmap, agoragentic_integrations, magg]
```

### database
```yaml
- id: database_t1_01
  tier: T1
  prompt: "Query PostgreSQL using mcp-server-postgres"
  target_tools: [mcp_server_postgres]

- id: database_t2_01
  tier: T2
  prompt: "Run analytics queries on our production database"
  target_tools: [mcp_server_postgres, anyquery]

- id: database_t3_01
  tier: T3
  prompt: "Pull metrics from our data warehouse with multiple sources"
  target_tools: [anyquery, mindsdb]
```

### notification
```yaml
- id: notification_t1_01
  tier: T1
  prompt: "Send Slack message using korotovsky slack-mcp-server"
  target_tools: [slack_mcp_server]

- id: notification_t2_01
  tier: T2
  prompt: "Notify team about deployment across chat platforms"
  target_tools: [slack_mcp_server, discord_mcp]

- id: notification_t3_01
  tier: T3
  prompt: "Alert stakeholders when build fails via any channel"
  target_tools: [slack_mcp_server, ntfy, pushover]
```
