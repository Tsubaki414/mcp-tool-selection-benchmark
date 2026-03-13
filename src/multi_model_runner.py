#!/usr/bin/env python3
"""
Multi-Model MCP Selection Benchmark Runner
Supports Claude and GPT-4 for cross-model comparison
"""

import asyncio
import json
import random
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import os

# Load API keys from .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key] = value

try:
    import anthropic
    import openai
except ImportError:
    print("Please install: pip install anthropic openai")
    exit(1)

# Configuration
MODELS = {
    "claude": "claude-sonnet-4-6",
    "gpt4": "gpt-4-turbo-preview",
    "gpt4o": "gpt-4o"
}
TEMPERATURE = 0
RUNS_PER_TASK = 10
MAX_CONCURRENT = 5

class MultiModelRunner:
    def __init__(self, data_dir: Path, db_path: Path, model_key: str = "claude"):
        self.data_dir = data_dir
        self.db_path = db_path
        self.model_key = model_key
        self.model_name = MODELS[model_key]
        
        # Initialize clients
        self.anthropic_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI()
        
        # Load data
        self.tools = self._load_tools()
        self.tasks = self._load_tasks()
        self.variants = self._load_variants()
        
        # Initialize database
        self._init_db()
    
    def _load_tools(self) -> dict:
        import yaml
        with open(self.data_dir / "tools.json") as f:
            data = json.load(f)
        return {t["id"]: t for t in data["tools"]}
    
    def _load_tasks(self) -> list:
        import yaml
        with open(self.data_dir / "tasks.yaml") as f:
            data = yaml.safe_load(f)
        return data["tasks"]
    
    def _load_variants(self) -> dict:
        with open(self.data_dir / "variants.json") as f:
            data = json.load(f)
        return {v["original_id"]: v for v in data["variants"]}
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS results (
                run_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                tier TEXT NOT NULL,
                cluster TEXT NOT NULL,
                pool_tool_ids TEXT NOT NULL,
                selected_tool_id TEXT,
                selection_type TEXT,
                is_variant_run INTEGER DEFAULT 0,
                variant_id TEXT,
                model TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                raw_response TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def get_cluster_tools(self, cluster: str) -> list:
        return [t for t in self.tools.values() if t["cluster"] == cluster]
    
    def tool_to_claude_format(self, tool: dict) -> dict:
        properties = {}
        required = []
        for param_name, param_spec in tool.get("parameters", {}).items():
            prop = {"type": param_spec.get("type", "string")}
            if "description" in param_spec:
                prop["description"] = param_spec["description"]
            if "enum" in param_spec:
                prop["enum"] = param_spec["enum"]
            properties[param_name] = prop
            if not param_spec.get("optional", False):
                required.append(param_name)
        
        return {
            "name": tool["id"],
            "description": tool["description"],
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    
    def tool_to_openai_format(self, tool: dict) -> dict:
        properties = {}
        required = []
        for param_name, param_spec in tool.get("parameters", {}).items():
            prop = {"type": param_spec.get("type", "string")}
            if "description" in param_spec:
                prop["description"] = param_spec["description"]
            if "enum" in param_spec:
                prop["enum"] = param_spec["enum"]
            properties[param_name] = prop
            if not param_spec.get("optional", False):
                required.append(param_name)
        
        return {
            "type": "function",
            "function": {
                "name": tool["id"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
    
    async def run_claude_test(self, task: dict, tool_pool: list) -> dict:
        shuffled_pool = tool_pool.copy()
        random.shuffle(shuffled_pool)
        claude_tools = [self.tool_to_claude_format(t) for t in shuffled_pool]
        
        try:
            response = self.anthropic_client.messages.create(
                model=self.model_name,
                max_tokens=1024,
                temperature=TEMPERATURE,
                tools=claude_tools,
                messages=[{"role": "user", "content": task["prompt"]}]
            )
            
            selected_tool = None
            mentioned_tool = None
            response_text = ""
            
            for block in response.content:
                if block.type == "tool_use":
                    selected_tool = block.name
                    break
                elif block.type == "text":
                    response_text += block.text
            
            if not selected_tool and response_text:
                for t in shuffled_pool:
                    if t["id"].lower() in response_text.lower():
                        mentioned_tool = t["id"]
                        break
            
            final_tool = selected_tool or mentioned_tool
            selection_type = "tool_use" if selected_tool else ("mentioned" if mentioned_tool else None)
            
            return {
                "selected_tool_id": final_tool,
                "selection_type": selection_type,
                "pool_tool_ids": [t["id"] for t in shuffled_pool],
                "raw_response": response.model_dump()
            }
        except Exception as e:
            print(f"Claude error: {e}")
            return None
    
    async def run_gpt_test(self, task: dict, tool_pool: list) -> dict:
        shuffled_pool = tool_pool.copy()
        random.shuffle(shuffled_pool)
        openai_tools = [self.tool_to_openai_format(t) for t in shuffled_pool]
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                temperature=TEMPERATURE,
                tools=openai_tools,
                messages=[{"role": "user", "content": task["prompt"]}]
            )
            
            selected_tool = None
            mentioned_tool = None
            response_text = ""
            
            message = response.choices[0].message
            
            # Check for tool calls
            if message.tool_calls:
                selected_tool = message.tool_calls[0].function.name
            
            # Check text content
            if message.content:
                response_text = message.content
            
            # Check for mentioned tools
            if not selected_tool and response_text:
                for t in shuffled_pool:
                    if t["id"].lower() in response_text.lower():
                        mentioned_tool = t["id"]
                        break
            
            final_tool = selected_tool or mentioned_tool
            selection_type = "tool_use" if selected_tool else ("mentioned" if mentioned_tool else None)
            
            return {
                "selected_tool_id": final_tool,
                "selection_type": selection_type,
                "pool_tool_ids": [t["id"] for t in shuffled_pool],
                "raw_response": response.model_dump()
            }
        except Exception as e:
            print(f"GPT error: {e}")
            return None
    
    async def run_single_test(self, task: dict, tool_pool: list) -> dict:
        if self.model_key == "claude":
            result = await self.run_claude_test(task, tool_pool)
        else:
            result = await self.run_gpt_test(task, tool_pool)
        
        if result is None:
            return None
        
        return {
            "run_id": str(uuid.uuid4()),
            "task_id": task["id"],
            "tier": task["tier"],
            "cluster": task["cluster"],
            "pool_tool_ids": json.dumps(result["pool_tool_ids"]),
            "selected_tool_id": result["selected_tool_id"],
            "selection_type": result["selection_type"],
            "is_variant_run": 0,
            "variant_id": None,
            "model": self.model_name,
            "timestamp": datetime.utcnow().isoformat(),
            "raw_response": json.dumps(result["raw_response"])
        }
    
    def save_result(self, result: dict):
        if result is None:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results (
                run_id, task_id, tier, cluster, pool_tool_ids,
                selected_tool_id, selection_type, is_variant_run, variant_id,
                model, timestamp, raw_response
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result["run_id"], result["task_id"], result["tier"], result["cluster"],
            result["pool_tool_ids"], result["selected_tool_id"], result["selection_type"],
            result["is_variant_run"], result["variant_id"], result["model"],
            result["timestamp"], result["raw_response"]
        ))
        conn.commit()
        conn.close()
    
    async def run_benchmark(self, clusters: list = None, runs_per_task: int = None):
        runs = runs_per_task or RUNS_PER_TASK
        print("=" * 60)
        print(f"BENCHMARK: {self.model_name}")
        print("=" * 60)
        
        total_runs = 0
        
        for task in self.tasks:
            cluster = task["cluster"]
            if clusters and cluster not in clusters:
                continue
            
            pool = self.get_cluster_tools(cluster)
            print(f"\nTask: {task['id']} ({task['tier']}) - {cluster}")
            
            for run_num in range(runs):
                result = await self.run_single_test(task, pool)
                self.save_result(result)
                
                if result:
                    selected = result["selected_tool_id"] or "NONE"
                    sel_type = result["selection_type"] or "none"
                    print(f"  Run {run_num + 1}: {selected} ({sel_type})")
                    total_runs += 1
                
                await asyncio.sleep(0.3)
        
        print(f"\nComplete: {total_runs} runs with {self.model_name}")
        return total_runs


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["claude", "gpt4", "gpt4o"], default="gpt4o")
    parser.add_argument("--clusters", nargs="+", help="Specific clusters to test")
    parser.add_argument("--runs", type=int, default=10, help="Runs per task")
    args = parser.parse_args()
    
    data_dir = Path(__file__).parent.parent / "data"
    db_path = data_dir / "results.db"
    
    runner = MultiModelRunner(data_dir, db_path, args.model)
    await runner.run_benchmark(clusters=args.clusters, runs_per_task=args.runs)


if __name__ == "__main__":
    asyncio.run(main())
