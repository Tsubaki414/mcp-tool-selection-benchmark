#!/usr/bin/env python3
"""
MCP Selection Benchmark V4 Runner
- Parallel Claude + GPT-4o execution
- Incremental save (resume on failure)
- Progress tracking
"""

import asyncio
import json
import os
import random
import sqlite3
import time
import uuid
import yaml
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Load API keys
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v

import anthropic
import openai

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
TOOLS_PATH = DATA_DIR / "tools_v4.json"
TASKS_PATH = DATA_DIR / "tasks_v4.yaml"
DB_PATH = DATA_DIR / "results_v4.db"
PROGRESS_PATH = DATA_DIR / "progress_v4.json"

# Config
MODELS = {
    "claude": "claude-sonnet-4-6",
    "gpt4o": "gpt-4o"
}
TEMPERATURE = 0
RUNS_PER_TASK = 10
MAX_CONCURRENT = 3  # Per model

# Clients
claude_client = anthropic.Anthropic()
openai_client = openai.OpenAI()

def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            run_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            tier TEXT NOT NULL,
            cluster TEXT NOT NULL,
            model TEXT NOT NULL,
            selected_tool_id TEXT,
            selection_type TEXT,
            target_tools TEXT,
            pool_size INTEGER,
            timestamp TEXT NOT NULL,
            latency_ms INTEGER,
            error TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_model ON results(task_id, model)
    """)
    conn.commit()
    conn.close()

def load_progress():
    """Load progress from file"""
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"completed": {}, "started_at": datetime.utcnow().isoformat()}

def save_progress(progress):
    """Save progress to file"""
    with open(PROGRESS_PATH, 'w') as f:
        json.dump(progress, f, indent=2)

def get_completed_runs(task_id, model):
    """Get number of completed runs for a task+model"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM results WHERE task_id = ? AND model = ?",
        (task_id, MODELS[model])
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count

def save_result(result):
    """Save a single result to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO results 
        (run_id, task_id, tier, cluster, model, selected_tool_id, 
         selection_type, target_tools, pool_size, timestamp, latency_ms, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result['run_id'],
        result['task_id'],
        result['tier'],
        result['cluster'],
        result['model'],
        result.get('selected_tool_id'),
        result.get('selection_type'),
        json.dumps(result.get('target_tools', [])),
        result.get('pool_size', 0),
        result['timestamp'],
        result.get('latency_ms'),
        result.get('error')
    ))
    conn.commit()
    conn.close()

def load_tools():
    """Load tools from JSON"""
    with open(TOOLS_PATH) as f:
        data = json.load(f)
    return {t['id']: t for t in data['tools']}

def load_tasks():
    """Load tasks from YAML"""
    with open(TASKS_PATH) as f:
        content = f.read()
    
    # Parse YAML (handle the generated format)
    tasks = []
    current_task = {}
    
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('- id:'):
            if current_task:
                tasks.append(current_task)
            current_task = {'id': line.split(':', 1)[1].strip()}
        elif line.startswith('cluster:'):
            current_task['cluster'] = line.split(':', 1)[1].strip()
        elif line.startswith('tier:'):
            current_task['tier'] = line.split(':', 1)[1].strip()
        elif line.startswith('prompt:'):
            current_task['prompt'] = line.split(':', 1)[1].strip().strip('"')
        elif line.startswith('target_tools:'):
            tools_str = line.split(':', 1)[1].strip()
            try:
                current_task['target_tools'] = eval(tools_str)
            except:
                current_task['target_tools'] = []
    
    if current_task:
        tasks.append(current_task)
    
    return [t for t in tasks if 'prompt' in t and t.get('prompt')]

def get_cluster_tools(cluster, all_tools):
    """Get tools for a specific cluster"""
    return [t for t in all_tools.values() if t['cluster'] == cluster]

def tool_to_claude_format(tool):
    """Convert tool to Claude format"""
    params = tool.get('parameters', [])
    properties = {}
    required = []
    
    for p in params:
        properties[p['name']] = {
            'type': p.get('type', 'string'),
            'description': p.get('description', f"The {p['name']} parameter")
        }
        if p.get('required', False):
            required.append(p['name'])
    
    return {
        'name': tool['id'],
        'description': tool['description'][:500],
        'input_schema': {
            'type': 'object',
            'properties': properties,
            'required': required
        }
    }

def tool_to_openai_format(tool):
    """Convert tool to OpenAI format"""
    params = tool.get('parameters', [])
    properties = {}
    required = []
    
    for p in params:
        prop = {'type': p.get('type', 'string')}
        prop['description'] = p.get('description', f"The {p['name']} parameter")
        properties[p['name']] = prop
        if p.get('required', False):
            required.append(p['name'])
    
    return {
        'type': 'function',
        'function': {
            'name': tool['id'],
            'description': tool['description'][:500],
            'parameters': {
                'type': 'object',
                'properties': properties,
                'required': required
            }
        }
    }

def run_claude_test(task, tool_pool):
    """Run a single Claude test"""
    start = time.time()
    shuffled = tool_pool.copy()
    random.shuffle(shuffled)
    tools = [tool_to_claude_format(t) for t in shuffled[:50]]  # Limit to 50 tools
    
    try:
        response = claude_client.messages.create(
            model=MODELS['claude'],
            max_tokens=1024,
            temperature=TEMPERATURE,
            tools=tools,
            messages=[{"role": "user", "content": task['prompt']}]
        )
        
        latency = int((time.time() - start) * 1000)
        
        selected = None
        sel_type = None
        
        for block in response.content:
            if block.type == "tool_use":
                selected = block.name
                sel_type = "tool_use"
                break
            elif block.type == "text":
                # Check for mentioned tools
                for t in shuffled:
                    if t['id'].lower() in block.text.lower():
                        selected = t['id']
                        sel_type = "mentioned"
                        break
        
        return {
            'selected_tool_id': selected,
            'selection_type': sel_type,
            'latency_ms': latency,
            'error': None
        }
    except Exception as e:
        return {
            'selected_tool_id': None,
            'selection_type': None,
            'latency_ms': int((time.time() - start) * 1000),
            'error': str(e)[:500]
        }

def run_gpt_test(task, tool_pool):
    """Run a single GPT-4o test"""
    start = time.time()
    shuffled = tool_pool.copy()
    random.shuffle(shuffled)
    tools = [tool_to_openai_format(t) for t in shuffled[:50]]
    
    try:
        response = openai_client.chat.completions.create(
            model=MODELS['gpt4o'],
            temperature=TEMPERATURE,
            tools=tools,
            messages=[{"role": "user", "content": task['prompt']}]
        )
        
        latency = int((time.time() - start) * 1000)
        
        selected = None
        sel_type = None
        msg = response.choices[0].message
        
        if msg.tool_calls:
            selected = msg.tool_calls[0].function.name
            sel_type = "tool_use"
        elif msg.content:
            for t in shuffled:
                if t['id'].lower() in msg.content.lower():
                    selected = t['id']
                    sel_type = "mentioned"
                    break
        
        return {
            'selected_tool_id': selected,
            'selection_type': sel_type,
            'latency_ms': latency,
            'error': None
        }
    except Exception as e:
        return {
            'selected_tool_id': None,
            'selection_type': None,
            'latency_ms': int((time.time() - start) * 1000),
            'error': str(e)[:500]
        }

def run_task(task, tool_pool, model, run_num):
    """Run a single task"""
    if model == 'claude':
        result = run_claude_test(task, tool_pool)
    else:
        result = run_gpt_test(task, tool_pool)
    
    result.update({
        'run_id': str(uuid.uuid4()),
        'task_id': task['id'],
        'tier': task.get('tier', 'unknown'),
        'cluster': task.get('cluster', 'unknown'),
        'model': MODELS[model],
        'target_tools': task.get('target_tools', []),
        'pool_size': len(tool_pool),
        'timestamp': datetime.utcnow().isoformat()
    })
    
    save_result(result)
    return result

async def run_benchmark():
    """Main benchmark runner"""
    print("=" * 60)
    print("MCP Selection Benchmark V4")
    print("=" * 60)
    
    init_db()
    progress = load_progress()
    all_tools = load_tools()
    tasks = load_tasks()
    
    print(f"\nLoaded: {len(all_tools)} tools, {len(tasks)} tasks")
    print(f"Models: Claude Sonnet 4.6, GPT-4o")
    print(f"Runs per task: {RUNS_PER_TASK}")
    
    # Group tasks by cluster
    by_cluster = {}
    for task in tasks:
        c = task.get('cluster', 'unknown')
        if c not in by_cluster:
            by_cluster[c] = []
        by_cluster[c].append(task)
    
    total_tasks = len(tasks) * 2  # Both models
    completed = 0
    
    print(f"\n{'='*60}")
    print("Starting benchmark...")
    print(f"{'='*60}\n")
    
    for cluster, cluster_tasks in by_cluster.items():
        tool_pool = get_cluster_tools(cluster, all_tools)
        if not tool_pool:
            print(f"⚠️  {cluster}: No tools found, skipping")
            continue
        
        print(f"\n📦 {cluster} ({len(tool_pool)} tools, {len(cluster_tasks)} tasks)")
        
        for task in cluster_tasks:
            for model in ['claude', 'gpt4o']:
                # Check how many runs already completed
                done = get_completed_runs(task['id'], model)
                remaining = RUNS_PER_TASK - done
                
                if remaining <= 0:
                    completed += 1
                    continue
                
                model_name = "Claude" if model == 'claude' else "GPT-4o"
                print(f"  [{model_name}] {task['id']}: ", end='', flush=True)
                
                successes = 0
                for run_num in range(remaining):
                    try:
                        result = run_task(task, tool_pool, model, done + run_num)
                        if result.get('selected_tool_id'):
                            successes += 1
                            print("✓", end='', flush=True)
                        else:
                            print("·", end='', flush=True)
                        
                        # Rate limiting
                        await asyncio.sleep(0.3)
                        
                    except Exception as e:
                        print(f"✗", end='', flush=True)
                        if "rate" in str(e).lower() or "quota" in str(e).lower():
                            print(f"\n⚠️  Rate limit hit. Waiting 60s...")
                            await asyncio.sleep(60)
                
                print(f" ({successes}/{remaining})")
                completed += 1
                
                # Save progress
                progress['completed'][f"{task['id']}_{model}"] = done + remaining
                progress['last_update'] = datetime.utcnow().isoformat()
                save_progress(progress)
    
    print(f"\n{'='*60}")
    print("Benchmark complete!")
    print(f"{'='*60}")
    
    # Summary
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM results")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT model, COUNT(*), SUM(CASE WHEN selected_tool_id IS NOT NULL THEN 1 ELSE 0 END) FROM results GROUP BY model")
    for row in cursor.fetchall():
        model, count, selected = row
        rate = 100 * selected / count if count > 0 else 0
        print(f"  {model}: {count} runs, {rate:.1f}% selection rate")
    
    conn.close()

if __name__ == '__main__':
    asyncio.run(run_benchmark())
