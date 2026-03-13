#!/usr/bin/env python3
"""
MCP Selection Benchmark Test Runner - Phase 4
Runs benchmark tests and records selection results
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

try:
    import anthropic
except ImportError:
    print("Please install anthropic: pip install anthropic")
    exit(1)

# Configuration
MODEL = "claude-sonnet-4-6"  # Use Claude Sonnet 4.6
TEMPERATURE = 0  # Deterministic for reproducibility
RUNS_PER_TASK = 10  # Number of times to run each task
MAX_CONCURRENT = 5  # Max concurrent API calls

class BenchmarkRunner:
    def __init__(self, data_dir: Path, db_path: Path):
        self.data_dir = data_dir
        self.db_path = db_path
        self.client = anthropic.Anthropic()
        
        # Load data
        self.tools = self._load_tools()
        self.tasks = self._load_tasks()
        self.variants = self._load_variants()
        
        # Initialize database
        self._init_db()
    
    def _load_tools(self) -> dict:
        """Load tools.json"""
        with open(self.data_dir / "tools.json") as f:
            data = json.load(f)
        # Index by ID
        return {t["id"]: t for t in data["tools"]}
    
    def _load_tasks(self) -> list:
        """Load tasks.yaml"""
        import yaml
        with open(self.data_dir / "tasks.yaml") as f:
            data = yaml.safe_load(f)
        return data["tasks"]
    
    def _load_variants(self) -> dict:
        """Load variants.json"""
        with open(self.data_dir / "variants.json") as f:
            data = json.load(f)
        # Index by original_id
        return {v["original_id"]: v for v in data["variants"]}
    
    def _init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Results table
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
        
        # Metrics table (computed after runs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                tool_id TEXT PRIMARY KEY,
                cluster TEXT NOT NULL,
                selection_rate_t1 REAL,
                selection_rate_t2 REAL,
                selection_rate_t3 REAL,
                cluster_percentile REAL,
                tier_delta REAL,
                ambiguity_resistance REAL,
                variant_lift REAL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_cluster_tools(self, cluster: str, include_variants: bool = False) -> list:
        """Get all tools in a cluster"""
        tools = [t for t in self.tools.values() if t["cluster"] == cluster]
        
        if include_variants:
            # Add variant versions
            for tool in tools[:]:
                if tool["id"] in self.variants:
                    variant = self.variants[tool["id"]]
                    variant_tool = tool.copy()
                    variant_tool["id"] = variant["variant_id"]
                    variant_tool["description"] = variant["variant_description"]
                    variant_tool["is_variant"] = True
                    variant_tool["variant_of"] = tool["id"]
                    tools.append(variant_tool)
        
        return tools
    
    def tool_to_claude_format(self, tool: dict) -> dict:
        """Convert tool to Claude's tool format"""
        # Build input schema from parameters
        properties = {}
        required = []
        
        for param_name, param_spec in tool.get("parameters", {}).items():
            prop = {"type": param_spec.get("type", "string")}
            if "description" in param_spec:
                prop["description"] = param_spec["description"]
            if "enum" in param_spec:
                prop["enum"] = param_spec["enum"]
            properties[param_name] = prop
            
            # Assume all params are required unless marked optional
            if not param_spec.get("optional", False):
                required.append(param_name)
        
        return {
            "name": tool["id"],  # Use ID as name for tracking
            "description": tool["description"],
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    
    async def run_single_test(
        self, 
        task: dict, 
        tool_pool: list,
        is_variant_run: bool = False,
        variant_id: Optional[str] = None
    ) -> dict:
        """Run a single test with the given task and tool pool"""
        
        # Shuffle pool to eliminate position bias
        shuffled_pool = tool_pool.copy()
        random.shuffle(shuffled_pool)
        
        # Convert tools to Claude format
        claude_tools = [self.tool_to_claude_format(t) for t in shuffled_pool]
        
        # Make API call
        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=1024,
                temperature=TEMPERATURE,
                tools=claude_tools,
                messages=[{
                    "role": "user",
                    "content": task["prompt"]
                }]
            )
            
            # Extract tool choice
            selected_tool = None
            mentioned_tool = None
            response_text = ""
            
            for block in response.content:
                if block.type == "tool_use":
                    selected_tool = block.name
                    break
                elif block.type == "text":
                    response_text += block.text
            
            # If no tool_use, check if model mentioned a tool by name
            if not selected_tool and response_text:
                tool_names = [t["id"] for t in shuffled_pool]
                for tool_name in tool_names:
                    # Check for exact tool name mention (case-insensitive)
                    if tool_name.lower() in response_text.lower():
                        mentioned_tool = tool_name
                        break
            
            # Use selected_tool if available, otherwise mentioned_tool
            final_tool = selected_tool or mentioned_tool
            selection_type = "tool_use" if selected_tool else ("mentioned" if mentioned_tool else None)
            
            return {
                "run_id": str(uuid.uuid4()),
                "task_id": task["id"],
                "tier": task["tier"],
                "cluster": task["cluster"],
                "pool_tool_ids": json.dumps([t["id"] for t in shuffled_pool]),
                "selected_tool_id": final_tool,
                "selection_type": selection_type,
                "is_variant_run": 1 if is_variant_run else 0,
                "variant_id": variant_id,
                "model": MODEL,
                "timestamp": datetime.utcnow().isoformat(),
                "raw_response": json.dumps(response.model_dump())
            }
            
        except Exception as e:
            print(f"Error running test: {e}")
            return None
    
    def save_result(self, result: dict):
        """Save a single result to database"""
        if result is None:
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO results (
                run_id, task_id, tier, cluster, pool_tool_ids,
                selected_tool_id, is_variant_run, variant_id,
                model, timestamp, raw_response
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result["run_id"],
            result["task_id"],
            result["tier"],
            result["cluster"],
            result["pool_tool_ids"],
            result["selected_tool_id"],
            result["is_variant_run"],
            result["variant_id"],
            result["model"],
            result["timestamp"],
            result["raw_response"]
        ))
        
        conn.commit()
        conn.close()
    
    async def run_main_benchmark(self):
        """Run the main benchmark (without variants)"""
        print("=" * 60)
        print("MAIN BENCHMARK")
        print("=" * 60)
        
        total_runs = 0
        
        for task in self.tasks:
            cluster = task["cluster"]
            pool = self.get_cluster_tools(cluster)
            
            print(f"\nTask: {task['id']} ({task['tier']})")
            print(f"  Cluster: {cluster} ({len(pool)} tools)")
            
            for run_num in range(RUNS_PER_TASK):
                result = await self.run_single_test(task, pool)
                self.save_result(result)
                
                if result:
                    selected = result["selected_tool_id"] or "NONE"
                    print(f"  Run {run_num + 1}: Selected {selected}")
                    total_runs += 1
                
                # Rate limiting
                await asyncio.sleep(0.2)
        
        print(f"\nMain benchmark complete: {total_runs} runs")
        return total_runs
    
    async def run_variant_benchmark(self):
        """Run variant comparison benchmark"""
        print("=" * 60)
        print("VARIANT BENCHMARK")
        print("=" * 60)
        
        total_runs = 0
        
        for original_id, variant_config in self.variants.items():
            if original_id not in self.tools:
                continue
                
            original_tool = self.tools[original_id]
            cluster = original_tool["cluster"]
            
            # Get tasks for this cluster
            cluster_tasks = [t for t in self.tasks if t["cluster"] == cluster]
            
            # Get other tools in cluster (excluding original)
            other_tools = [t for t in self.get_cluster_tools(cluster) 
                          if t["id"] != original_id]
            
            print(f"\nVariant test: {original_id} -> {variant_config['variant_id']}")
            print(f"  Feature: {variant_config['feature_changed']}")
            
            for task in cluster_tasks:
                # Run with original
                pool_original = [original_tool] + other_tools
                result_orig = await self.run_single_test(
                    task, pool_original, 
                    is_variant_run=True, 
                    variant_id=f"{original_id}_original"
                )
                self.save_result(result_orig)
                
                # Run with variant
                variant_tool = original_tool.copy()
                variant_tool["id"] = variant_config["variant_id"]
                variant_tool["description"] = variant_config["variant_description"]
                
                pool_variant = [variant_tool] + other_tools
                result_var = await self.run_single_test(
                    task, pool_variant,
                    is_variant_run=True,
                    variant_id=variant_config["variant_id"]
                )
                self.save_result(result_var)
                
                if result_orig and result_var:
                    orig_selected = result_orig["selected_tool_id"] == original_id
                    var_selected = result_var["selected_tool_id"] == variant_config["variant_id"]
                    print(f"  {task['id']}: orig={orig_selected}, var={var_selected}")
                    total_runs += 2
                
                await asyncio.sleep(0.2)
        
        print(f"\nVariant benchmark complete: {total_runs} runs")
        return total_runs
    
    async def run_full_benchmark(self):
        """Run complete benchmark suite"""
        print("Starting MCP Selection Benchmark v3")
        print(f"Model: {MODEL}")
        print(f"Tools: {len(self.tools)}")
        print(f"Tasks: {len(self.tasks)}")
        print(f"Variants: {len(self.variants)}")
        print()
        
        main_runs = await self.run_main_benchmark()
        variant_runs = await self.run_variant_benchmark()
        
        print("\n" + "=" * 60)
        print("BENCHMARK COMPLETE")
        print("=" * 60)
        print(f"Total runs: {main_runs + variant_runs}")
        print(f"Results saved to: {self.db_path}")
    
    def dry_run(self):
        """Do a dry run without API calls to verify setup"""
        print("DRY RUN - Verifying setup")
        print()
        
        print(f"Tools loaded: {len(self.tools)}")
        for cluster in set(t["cluster"] for t in self.tools.values()):
            count = len([t for t in self.tools.values() if t["cluster"] == cluster])
            print(f"  {cluster}: {count} tools")
        
        print(f"\nTasks loaded: {len(self.tasks)}")
        for tier in ["T1", "T2", "T3"]:
            count = len([t for t in self.tasks if t["tier"] == tier])
            print(f"  {tier}: {count} tasks")
        
        print(f"\nVariants loaded: {len(self.variants)}")
        
        # Test tool conversion
        sample_tool = list(self.tools.values())[0]
        claude_format = self.tool_to_claude_format(sample_tool)
        print(f"\nSample tool conversion:")
        print(f"  Name: {claude_format['name']}")
        print(f"  Description length: {len(claude_format['description'])}")
        
        print("\nDry run complete - ready to run benchmark")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Selection Benchmark Runner")
    parser.add_argument("--mode", choices=["full", "main", "variants", "dry"],
                       default="dry", help="Run mode")
    parser.add_argument("--data-dir", type=Path, 
                       default=Path(__file__).parent.parent / "data",
                       help="Data directory")
    parser.add_argument("--db", type=Path,
                       default=Path(__file__).parent.parent / "data" / "results.db",
                       help="Output database path")
    
    args = parser.parse_args()
    
    runner = BenchmarkRunner(args.data_dir, args.db)
    
    if args.mode == "dry":
        runner.dry_run()
    elif args.mode == "main":
        await runner.run_main_benchmark()
    elif args.mode == "variants":
        await runner.run_variant_benchmark()
    elif args.mode == "full":
        await runner.run_full_benchmark()


if __name__ == "__main__":
    asyncio.run(main())
