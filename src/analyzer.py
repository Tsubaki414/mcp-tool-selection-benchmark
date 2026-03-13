#!/usr/bin/env python3
"""
MCP Selection Benchmark Analyzer - Phase 6
Computes metrics and generates reports
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

class BenchmarkAnalyzer:
    def __init__(self, db_path: Path, data_dir: Path):
        self.db_path = db_path
        self.data_dir = data_dir
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        
        # Load tool metadata
        with open(data_dir / "tools.json") as f:
            data = json.load(f)
            self.tools = {t["id"]: t for t in data["tools"]}
        
        # Load variant metadata
        with open(data_dir / "variants.json") as f:
            data = json.load(f)
            self.variants = {v["original_id"]: v for v in data["variants"]}
    
    def compute_selection_rates(self) -> Dict[str, Dict]:
        """Compute selection rates for each tool by tier"""
        cursor = self.conn.cursor()
        
        metrics = defaultdict(lambda: {
            "T1": {"selected": 0, "total": 0},
            "T2": {"selected": 0, "total": 0},
            "T3": {"selected": 0, "total": 0}
        })
        
        # Count selections (excluding variant runs)
        cursor.execute("""
            SELECT task_id, tier, cluster, pool_tool_ids, selected_tool_id
            FROM results
            WHERE is_variant_run = 0
        """)
        
        for row in cursor.fetchall():
            pool = json.loads(row["pool_tool_ids"])
            tier = row["tier"]
            selected = row["selected_tool_id"]
            
            for tool_id in pool:
                metrics[tool_id][tier]["total"] += 1
                if tool_id == selected:
                    metrics[tool_id][tier]["selected"] += 1
        
        # Calculate rates
        results = {}
        for tool_id, tier_data in metrics.items():
            results[tool_id] = {
                "selection_rate_T1": tier_data["T1"]["selected"] / max(tier_data["T1"]["total"], 1),
                "selection_rate_T2": tier_data["T2"]["selected"] / max(tier_data["T2"]["total"], 1),
                "selection_rate_T3": tier_data["T3"]["selected"] / max(tier_data["T3"]["total"], 1),
                "total_selections": sum(t["selected"] for t in tier_data.values()),
                "total_appearances": sum(t["total"] for t in tier_data.values())
            }
        
        return results
    
    def compute_cluster_percentiles(self, selection_rates: Dict) -> Dict[str, float]:
        """Compute percentile rank within each cluster"""
        # Group by cluster
        clusters = defaultdict(list)
        for tool_id, rates in selection_rates.items():
            if tool_id in self.tools:
                cluster = self.tools[tool_id]["cluster"]
                overall_rate = (rates["selection_rate_T1"] + 
                               rates["selection_rate_T2"] + 
                               rates["selection_rate_T3"]) / 3
                clusters[cluster].append((tool_id, overall_rate))
        
        # Compute percentiles
        percentiles = {}
        for cluster, tools in clusters.items():
            sorted_tools = sorted(tools, key=lambda x: x[1], reverse=True)
            n = len(sorted_tools)
            for rank, (tool_id, rate) in enumerate(sorted_tools):
                percentile = ((n - rank) / n) * 100
                percentiles[tool_id] = percentile
        
        return percentiles
    
    def compute_variant_lift(self) -> Dict[str, Dict]:
        """Compute lift from variant changes"""
        cursor = self.conn.cursor()
        
        lifts = {}
        
        for original_id, variant_config in self.variants.items():
            variant_id = variant_config["variant_id"]
            
            # Get selection counts for original
            cursor.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN selected_tool_id = ? THEN 1 ELSE 0 END) as selected
                FROM results
                WHERE is_variant_run = 1 AND variant_id = ?
            """, (original_id, f"{original_id}_original"))
            
            orig_row = cursor.fetchone()
            orig_rate = orig_row["selected"] / max(orig_row["total"], 1) if orig_row else 0
            
            # Get selection counts for variant
            cursor.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN selected_tool_id = ? THEN 1 ELSE 0 END) as selected
                FROM results
                WHERE is_variant_run = 1 AND variant_id = ?
            """, (variant_id, variant_id))
            
            var_row = cursor.fetchone()
            var_rate = var_row["selected"] / max(var_row["total"], 1) if var_row else 0
            
            lifts[original_id] = {
                "feature_changed": variant_config["feature_changed"],
                "original_rate": orig_rate,
                "variant_rate": var_rate,
                "lift": var_rate - orig_rate,
                "lift_pct": ((var_rate - orig_rate) / max(orig_rate, 0.01)) * 100
            }
        
        return lifts
    
    def compute_all_metrics(self) -> Dict:
        """Compute all metrics"""
        selection_rates = self.compute_selection_rates()
        percentiles = self.compute_cluster_percentiles(selection_rates)
        variant_lifts = self.compute_variant_lift()
        
        metrics = {}
        
        for tool_id in self.tools:
            rates = selection_rates.get(tool_id, {
                "selection_rate_T1": 0,
                "selection_rate_T2": 0,
                "selection_rate_T3": 0
            })
            
            # Tier delta: T3 - T1 (negative = loses head-to-head)
            tier_delta = rates.get("selection_rate_T3", 0) - rates.get("selection_rate_T1", 0)
            
            # Ambiguity resistance: T2 / T1
            t1_rate = rates.get("selection_rate_T1", 0)
            t2_rate = rates.get("selection_rate_T2", 0)
            ambiguity_resistance = t2_rate / t1_rate if t1_rate > 0 else None
            
            metrics[tool_id] = {
                "cluster": self.tools[tool_id]["cluster"],
                "selection_rate_T1": rates.get("selection_rate_T1", 0),
                "selection_rate_T2": rates.get("selection_rate_T2", 0),
                "selection_rate_T3": rates.get("selection_rate_T3", 0),
                "cluster_percentile": percentiles.get(tool_id, 50),
                "tier_delta": tier_delta,
                "ambiguity_resistance": ambiguity_resistance,
                "variant_lift": variant_lifts.get(tool_id)
            }
        
        return metrics
    
    def generate_cluster_rankings(self, metrics: Dict) -> Dict[str, List]:
        """Generate rankings for each cluster"""
        clusters = defaultdict(list)
        
        for tool_id, m in metrics.items():
            clusters[m["cluster"]].append({
                "tool_id": tool_id,
                "overall_rate": (m["selection_rate_T1"] + m["selection_rate_T2"] + m["selection_rate_T3"]) / 3,
                "percentile": m["cluster_percentile"]
            })
        
        rankings = {}
        for cluster, tools in clusters.items():
            sorted_tools = sorted(tools, key=lambda x: x["overall_rate"], reverse=True)
            for rank, tool in enumerate(sorted_tools, 1):
                tool["rank"] = rank
            rankings[cluster] = sorted_tools
        
        return rankings
    
    def generate_report(self, metrics: Dict, rankings: Dict) -> str:
        """Generate markdown analysis report"""
        report = []
        report.append("# MCP Selection Benchmark Analysis Report")
        report.append(f"\nGenerated: {self._get_timestamp()}")
        report.append(f"\nModel: claude-sonnet-4-5-20250514")
        report.append("")
        
        # Executive Summary
        report.append("## Executive Summary")
        report.append("")
        
        # Count stats
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM results WHERE is_variant_run = 0")
        main_runs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM results WHERE is_variant_run = 1")
        variant_runs = cursor.fetchone()[0]
        
        report.append(f"- Total test runs: {main_runs + variant_runs}")
        report.append(f"- Main benchmark runs: {main_runs}")
        report.append(f"- Variant comparison runs: {variant_runs}")
        report.append(f"- Tools tested: {len(self.tools)}")
        report.append(f"- Clusters: {len(rankings)}")
        report.append("")
        
        # Cluster Rankings
        report.append("## Cluster Rankings")
        report.append("")
        
        for cluster, tools in rankings.items():
            report.append(f"### {cluster.upper()}")
            report.append("")
            report.append("| Rank | Tool | Selection Rate | Percentile |")
            report.append("|------|------|----------------|------------|")
            for tool in tools[:5]:  # Top 5
                rate = f"{tool['overall_rate']*100:.1f}%"
                pct = f"P{tool['percentile']:.0f}"
                report.append(f"| {tool['rank']} | {tool['tool_id']} | {rate} | {pct} |")
            report.append("")
        
        # Feature Lift Analysis
        report.append("## Feature Lift Analysis")
        report.append("")
        report.append("Impact of description features on selection rate:")
        report.append("")
        
        # Aggregate lifts by feature
        feature_lifts = defaultdict(list)
        for tool_id, m in metrics.items():
            if m["variant_lift"]:
                feature = m["variant_lift"]["feature_changed"]
                lift = m["variant_lift"]["lift"]
                feature_lifts[feature].append(lift)
        
        report.append("| Feature | Avg Lift | Samples |")
        report.append("|---------|----------|---------|")
        for feature, lifts in sorted(feature_lifts.items(), key=lambda x: -sum(x[1])/len(x[1])):
            avg_lift = sum(lifts) / len(lifts)
            report.append(f"| {feature} | {avg_lift*100:+.1f}pp | {len(lifts)} |")
        report.append("")
        
        # Recommendations
        report.append("## Recommendations")
        report.append("")
        report.append("Based on the benchmark results:")
        report.append("")
        report.append("### For Tool Developers")
        report.append("")
        
        for feature, lifts in sorted(feature_lifts.items(), key=lambda x: -sum(x[1])/len(x[1])):
            avg_lift = sum(lifts) / len(lifts)
            if avg_lift > 0:
                report.append(f"- **{feature}**: Adding this improves selection by {avg_lift*100:+.1f}pp on average")
        
        report.append("")
        report.append("### Tools Needing Improvement")
        report.append("")
        
        # Find tools with low T2 performance
        for tool_id, m in metrics.items():
            if m["ambiguity_resistance"] and m["ambiguity_resistance"] < 0.5:
                report.append(f"- **{tool_id}**: Low ambiguity resistance ({m['ambiguity_resistance']:.2f}). Consider adding examples or negative cases.")
        
        return "\n".join(report)
    
    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    def save_metrics(self, metrics: Dict):
        """Save computed metrics to database"""
        cursor = self.conn.cursor()
        
        for tool_id, m in metrics.items():
            cursor.execute("""
                INSERT OR REPLACE INTO metrics (
                    tool_id, cluster, selection_rate_t1, selection_rate_t2,
                    selection_rate_t3, cluster_percentile, tier_delta,
                    ambiguity_resistance, variant_lift
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tool_id,
                m["cluster"],
                m["selection_rate_T1"],
                m["selection_rate_T2"],
                m["selection_rate_T3"],
                m["cluster_percentile"],
                m["tier_delta"],
                m["ambiguity_resistance"],
                json.dumps(m["variant_lift"]) if m["variant_lift"] else None
            ))
        
        self.conn.commit()
    
    def export_csv(self, rankings: Dict, output_path: Path):
        """Export cluster rankings to CSV"""
        with open(output_path, "w") as f:
            f.write("cluster,rank,tool_id,selection_rate,percentile\n")
            for cluster, tools in rankings.items():
                for tool in tools:
                    f.write(f"{cluster},{tool['rank']},{tool['tool_id']},{tool['overall_rate']:.4f},{tool['percentile']:.0f}\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Selection Benchmark Analyzer")
    parser.add_argument("--db", type=Path, 
                       default=Path(__file__).parent.parent / "data" / "results.db",
                       help="Results database")
    parser.add_argument("--data-dir", type=Path,
                       default=Path(__file__).parent.parent / "data",
                       help="Data directory")
    parser.add_argument("--output-dir", type=Path,
                       default=Path(__file__).parent.parent / "reports",
                       help="Output directory for reports")
    
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    analyzer = BenchmarkAnalyzer(args.db, args.data_dir)
    
    print("Computing metrics...")
    metrics = analyzer.compute_all_metrics()
    
    print("Generating rankings...")
    rankings = analyzer.generate_cluster_rankings(metrics)
    
    print("Saving metrics to database...")
    analyzer.save_metrics(metrics)
    
    print("Generating report...")
    report = analyzer.generate_report(metrics, rankings)
    
    report_path = args.output_dir / "analysis.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved to: {report_path}")
    
    csv_path = args.output_dir / "cluster_rankings.csv"
    analyzer.export_csv(rankings, csv_path)
    print(f"CSV saved to: {csv_path}")
    
    # Print summary
    print("\n" + "=" * 50)
    print("ANALYSIS COMPLETE")
    print("=" * 50)
    
    # Quick summary
    for cluster, tools in list(rankings.items())[:3]:
        print(f"\n{cluster.upper()} Top 3:")
        for tool in tools[:3]:
            print(f"  {tool['rank']}. {tool['tool_id']} ({tool['overall_rate']*100:.1f}%)")


if __name__ == "__main__":
    main()
