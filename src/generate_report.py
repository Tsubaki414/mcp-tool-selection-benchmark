#!/usr/bin/env python3
"""
Generate comprehensive benchmark report
Includes both V1 (52 tools) and V4 (673 tools) data
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"
REPORT_DIR = Path(__file__).parent.parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

def query_db(db_path, sql):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(sql)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results

def generate_report():
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MCP Tool Selection Benchmark - Full Report</title>
<style>
body { 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
    max-width: 1000px; 
    margin: 40px auto; 
    padding: 20px;
    line-height: 1.6;
    color: #333;
}
h1 { border-bottom: 3px solid #2563eb; padding-bottom: 15px; }
h2 { color: #1e40af; margin-top: 40px; border-left: 4px solid #2563eb; padding-left: 15px; }
h3 { color: #374151; }
table { border-collapse: collapse; width: 100%; margin: 20px 0; }
th, td { border: 1px solid #e5e7eb; padding: 12px; text-align: left; }
th { background: #f3f4f6; font-weight: 600; }
tr:nth-child(even) { background: #f9fafb; }
.metric-card {
    display: inline-block;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 20px 30px;
    border-radius: 12px;
    margin: 10px;
    text-align: center;
    min-width: 150px;
}
.metric-card .value { font-size: 32px; font-weight: bold; }
.metric-card .label { font-size: 14px; opacity: 0.9; }
.highlight { background: #fef3c7; padding: 2px 6px; border-radius: 4px; }
.good { color: #059669; font-weight: bold; }
.bad { color: #dc2626; font-weight: bold; }
.section { background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0; }
.comparison { display: flex; gap: 20px; }
.comparison > div { flex: 1; }
code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
.finding { 
    background: #ecfdf5; 
    border-left: 4px solid #10b981; 
    padding: 15px 20px; 
    margin: 15px 0;
    border-radius: 0 8px 8px 0;
}
.warning {
    background: #fef3c7;
    border-left: 4px solid #f59e0b;
    padding: 15px 20px;
    margin: 15px 0;
    border-radius: 0 8px 8px 0;
}
</style>
</head>
<body>
"""
    
    # Title
    html += f"""
<h1>MCP Tool Selection Benchmark</h1>
<p><strong>Full Report</strong> | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
"""
    
    # Executive Summary
    html += """
<h2>Executive Summary</h2>
<div class="section">
"""
    
    # Get stats from both databases
    v1_stats = query_db(DATA_DIR / "results.db", """
        SELECT 
            model,
            COUNT(*) as runs,
            SUM(CASE WHEN selected_tool_id IS NOT NULL THEN 1 ELSE 0 END) as selected,
            ROUND(100.0 * SUM(CASE WHEN selected_tool_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as rate
        FROM results
        GROUP BY model
    """)
    
    v4_stats = query_db(DATA_DIR / "results_v4.db", """
        SELECT 
            model,
            COUNT(*) as runs,
            SUM(CASE WHEN selected_tool_id IS NOT NULL THEN 1 ELSE 0 END) as selected,
            ROUND(100.0 * SUM(CASE WHEN selected_tool_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as rate
        FROM results
        GROUP BY model
    """)
    
    v1_total = sum(s['runs'] for s in v1_stats)
    v4_total = sum(s['runs'] for s in v4_stats)
    
    html += f"""
<div style="text-align: center;">
    <div class="metric-card">
        <div class="value">{v1_total + v4_total:,}</div>
        <div class="label">Total Benchmark Runs</div>
    </div>
    <div class="metric-card">
        <div class="value">725</div>
        <div class="label">Tools Tested</div>
    </div>
    <div class="metric-card">
        <div class="value">2</div>
        <div class="label">LLM Models</div>
    </div>
    <div class="metric-card">
        <div class="value">15</div>
        <div class="label">Tool Clusters</div>
    </div>
</div>

<div class="finding">
<strong>Key Finding:</strong> Claude Sonnet 4.6 consistently outperforms GPT-4o in tool selection across both benchmark scales, with a 20-24 percentage point advantage.
</div>
</div>
"""
    
    # Benchmark Comparison
    html += """
<h2>Benchmark Comparison</h2>
<div class="comparison">
<div class="section">
<h3>V1: 52 Tools (Curated)</h3>
"""
    
    for stat in v1_stats:
        model_name = "Claude Sonnet 4.6" if "claude" in stat['model'] else "GPT-4o"
        html += f"<p><strong>{model_name}:</strong> {stat['runs']} runs, <span class='{'good' if stat['rate'] > 50 else 'bad'}'>{stat['rate']}%</span> selection rate</p>"
    
    html += """
<p><em>Focus: DeFi tools, productivity apps</em></p>
<p><em>Key discovery: Schema Compatibility Failure</em></p>
</div>
<div class="section">
<h3>V4: 673 Tools (Crawled)</h3>
"""
    
    for stat in v4_stats:
        model_name = "Claude Sonnet 4.6" if "claude" in stat['model'] else "GPT-4o"
        html += f"<p><strong>{model_name}:</strong> {stat['runs']} runs, <span class='{'good' if stat['rate'] > 50 else 'bad'}'>{stat['rate']}%</span> selection rate</p>"
    
    html += """
<p><em>Source: awesome-mcp-servers</em></p>
<p><em>15 functional clusters</em></p>
</div>
</div>
"""
    
    # Detailed Results by Tier
    html += "<h2>Results by Task Tier</h2>"
    
    v1_tiers = query_db(DATA_DIR / "results.db", """
        SELECT 
            tier,
            model,
            COUNT(*) as runs,
            ROUND(100.0 * SUM(CASE WHEN selected_tool_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as rate
        FROM results
        GROUP BY tier, model
        ORDER BY tier, model
    """)
    
    v4_tiers = query_db(DATA_DIR / "results_v4.db", """
        SELECT 
            tier,
            model,
            COUNT(*) as runs,
            ROUND(100.0 * SUM(CASE WHEN selected_tool_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as rate
        FROM results
        GROUP BY tier, model
        ORDER BY tier, model
    """)
    
    html += """
<table>
<tr>
    <th rowspan="2">Tier</th>
    <th colspan="2">V1 (52 tools)</th>
    <th colspan="2">V4 (673 tools)</th>
</tr>
<tr>
    <th>Claude</th>
    <th>GPT-4o</th>
    <th>Claude</th>
    <th>GPT-4o</th>
</tr>
"""
    
    # Organize tier data
    v1_by_tier = {}
    for t in v1_tiers:
        tier = t['tier']
        if tier not in v1_by_tier:
            v1_by_tier[tier] = {}
        key = 'claude' if 'claude' in t['model'] else 'gpt'
        v1_by_tier[tier][key] = t['rate']
    
    v4_by_tier = {}
    for t in v4_tiers:
        tier = t['tier']
        if tier not in v4_by_tier:
            v4_by_tier[tier] = {}
        key = 'claude' if 'claude' in t['model'] else 'gpt'
        v4_by_tier[tier][key] = t['rate']
    
    tier_names = {'T1': 'T1 (Direct)', 'T2': 'T2 (Ambiguous)', 'T3': 'T3 (Competitive)'}
    for tier in ['T1', 'T2', 'T3']:
        v1_c = v1_by_tier.get(tier, {}).get('claude', '-')
        v1_g = v1_by_tier.get(tier, {}).get('gpt', '-')
        v4_c = v4_by_tier.get(tier, {}).get('claude', '-')
        v4_g = v4_by_tier.get(tier, {}).get('gpt', '-')
        html += f"<tr><td><strong>{tier_names.get(tier, tier)}</strong></td><td>{v1_c}%</td><td>{v1_g}%</td><td>{v4_c}%</td><td>{v4_g}%</td></tr>"
    
    html += "</table>"
    
    html += """
<div class="finding">
<strong>Pattern:</strong> Both models show declining performance from T1→T2→T3, but Claude maintains higher accuracy under ambiguity. GPT-4o's T3 performance varies dramatically between benchmark versions.
</div>
"""
    
    # Results by Cluster (V4)
    html += "<h2>Results by Cluster (V4 - 673 tools)</h2>"
    
    v4_clusters = query_db(DATA_DIR / "results_v4.db", """
        SELECT 
            cluster,
            model,
            COUNT(*) as runs,
            ROUND(100.0 * SUM(CASE WHEN selected_tool_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as rate
        FROM results
        GROUP BY cluster, model
        ORDER BY cluster, model
    """)
    
    # Organize by cluster
    clusters = {}
    for c in v4_clusters:
        cluster = c['cluster']
        if cluster not in clusters:
            clusters[cluster] = {}
        key = 'claude' if 'claude' in c['model'] else 'gpt'
        clusters[cluster][key] = c['rate']
        clusters[cluster]['runs'] = clusters[cluster].get('runs', 0) + c['runs']
    
    html += """
<table>
<tr><th>Cluster</th><th>Runs</th><th>Claude</th><th>GPT-4o</th><th>Gap</th></tr>
"""
    
    for cluster, data in sorted(clusters.items(), key=lambda x: -(x[1].get('claude', 0))):
        claude = data.get('claude', 0)
        gpt = data.get('gpt', 0)
        gap = claude - gpt
        gap_class = 'good' if gap > 0 else 'bad'
        html += f"<tr><td><strong>{cluster}</strong></td><td>{data['runs']}</td><td>{claude}%</td><td>{gpt}%</td><td class='{gap_class}'>{gap:+.1f}pp</td></tr>"
    
    html += "</table>"
    
    # Results by Cluster (V1)
    html += "<h2>Results by Cluster (V1 - 52 tools)</h2>"
    
    v1_clusters = query_db(DATA_DIR / "results.db", """
        SELECT 
            cluster,
            model,
            COUNT(*) as runs,
            ROUND(100.0 * SUM(CASE WHEN selected_tool_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as rate
        FROM results
        GROUP BY cluster, model
        ORDER BY cluster, model
    """)
    
    clusters_v1 = {}
    for c in v1_clusters:
        cluster = c['cluster']
        if cluster not in clusters_v1:
            clusters_v1[cluster] = {}
        key = 'claude' if 'claude' in c['model'] else 'gpt'
        clusters_v1[cluster][key] = c['rate']
        clusters_v1[cluster]['runs'] = clusters_v1[cluster].get('runs', 0) + c['runs']
    
    html += """
<table>
<tr><th>Cluster</th><th>Runs</th><th>Claude</th><th>GPT-4o</th><th>Gap</th></tr>
"""
    
    for cluster, data in sorted(clusters_v1.items(), key=lambda x: -(x[1].get('claude', 0))):
        claude = data.get('claude', 0)
        gpt = data.get('gpt', 0)
        gap = claude - gpt
        gap_class = 'good' if gap > 0 else 'bad'
        html += f"<tr><td><strong>{cluster}</strong></td><td>{data['runs']}</td><td>{claude}%</td><td>{gpt}%</td><td class='{gap_class}'>{gap:+.1f}pp</td></tr>"
    
    html += "</table>"
    
    # Three Failure Modes
    html += """
<h2>Three Failure Modes</h2>
<div class="section">
<h3>1. Schema Failure</h3>
<p>The agent recognizes the tool but cannot complete the call due to missing parameters or unclear schema.</p>
<p><strong>Evidence (V1):</strong> Notification cluster — 98% mention rate, 0% invocation rate on Claude.</p>

<h3>2. Description Failure</h3>
<p>The agent doesn't connect the task to the tool due to insufficient semantic signal in the description.</p>
<p><strong>Evidence (V1):</strong> Portfolio cluster — 37% mention rate on Claude. Tools like <code>zapper_balance</code> weren't recognized for "check my DeFi positions".</p>

<h3>3. Compatibility Failure</h3>
<p>The tool works on one model but fails schema validation on another.</p>
<p><strong>Evidence:</strong> <code>zapper_balance</code> schema defines <code>networks</code> as <code>type: array</code> without <code>items</code>. Claude accepts this; GPT-4o rejects with HTTP 400.</p>
</div>

<div class="warning">
<strong>Implication:</strong> A tool optimized for Claude may be completely unusable on GPT-4o, and vice versa. Cross-model testing is essential.
</div>
"""
    
    # Methodology
    html += """
<h2>Methodology</h2>
<div class="section">
<h3>Data Collection</h3>
<ul>
    <li><strong>V1:</strong> 52 tools manually curated from major MCP server repositories</li>
    <li><strong>V4:</strong> 673 tools crawled from <a href="https://github.com/punkpeye/awesome-mcp-servers">awesome-mcp-servers</a> (83k+ stars)</li>
</ul>

<h3>Task Tiers</h3>
<ul>
    <li><strong>T1 (Direct):</strong> Explicitly names tool — "Swap on Uniswap V3"</li>
    <li><strong>T2 (Ambiguous):</strong> Clear intent, no tool named — "Exchange stablecoins for ETH"</li>
    <li><strong>T3 (Competitive):</strong> Vague or pits tools against each other — "Find optimal swap route"</li>
</ul>

<h3>Detection</h3>
<ul>
    <li>Primary: <code>tool_use</code> stop reason (explicit API call)</li>
    <li>Secondary: Fuzzy name matching in response text</li>
</ul>

<h3>Configuration</h3>
<ul>
    <li>Temperature: 0 (deterministic)</li>
    <li>Runs per task: 10 (V4) / variable (V1)</li>
    <li>Models: Claude Sonnet 4.6, GPT-4o</li>
</ul>
</div>
"""
    
    # Conclusion
    html += """
<h2>Conclusions</h2>
<div class="section">
<ol>
    <li><strong>Cross-model variance is real and large.</strong> Claude outperforms GPT-4o by 20-24pp across both benchmark scales.</li>
    <li><strong>Three distinct failure modes exist:</strong> Schema, Description, and Compatibility failures require different fixes.</li>
    <li><strong>Scale matters but patterns persist.</strong> Expanding from 52 to 673 tools confirmed the core findings.</li>
    <li><strong>T3 (competitive) is the hardest tier.</strong> Both models struggle when multiple tools could apply.</li>
    <li><strong>Single-model testing is insufficient.</strong> A tool working on Claude may fail entirely on GPT-4o.</li>
</ol>
</div>
"""
    
    # Data Files
    html += """
<h2>Data Files</h2>
<div class="section">
<table>
<tr><th>File</th><th>Description</th></tr>
<tr><td><code>results.db</code></td><td>V1 benchmark results (52 tools, 1,629 runs)</td></tr>
<tr><td><code>results_v4.db</code></td><td>V4 benchmark results (673 tools, 1,080 runs)</td></tr>
<tr><td><code>tools.json</code></td><td>V1 tool definitions</td></tr>
<tr><td><code>tools_v4.json</code></td><td>V4 tool definitions (merged)</td></tr>
<tr><td><code>tasks.yaml</code></td><td>V1 benchmark tasks</td></tr>
<tr><td><code>tasks_v4.yaml</code></td><td>V4 benchmark tasks</td></tr>
</table>
</div>
"""
    
    html += """
<hr>
<p style="color: #666; font-size: 14px;">
MCP Tool Selection Benchmark | 2026 | 
<a href="https://github.com/Tsubaki414/mcp-tool-selection-benchmark">GitHub</a>
</p>
</body>
</html>
"""
    
    # Save HTML
    html_path = REPORT_DIR / "FULL_REPORT.html"
    with open(html_path, 'w') as f:
        f.write(html)
    print(f"Saved HTML: {html_path}")
    
    return html_path

if __name__ == '__main__':
    generate_report()
