#!/usr/bin/env python3
"""
Financial Weaknesses Trend Analyzer
Analyzes trends across multiple monitoring reports to detect:
1. Escalation/de-escalation of traditional financial API blocking
2. Changes in selective service restriction patterns
3. Long-term trend analysis
"""

import json
import os
import glob
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import statistics

class FinancialWeaknessesTrendAnalyzer:
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.analysis_id = f"FWT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self.monitoring_dir = "/root/.openclaw/workspace/monitoring"
        self.trends_dir = "/root/.openclaw/workspace/trends"
        os.makedirs(self.trends_dir, exist_ok=True)
        
        self.report_file = os.path.join(
            self.trends_dir,
            f"financial-weaknesses-trends-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.json"
        )
        
    def load_monitoring_reports(self, hours_back: int = 24) -> List[Dict]:
        """Load monitoring reports from the last N hours"""
        reports = []
        pattern = os.path.join(self.monitoring_dir, "financial-weaknesses-*.json")
        
        for file_path in glob.glob(pattern):
            try:
                # Check file age
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - file_mtime).total_seconds() / 3600
                
                if age_hours <= hours_back:
                    with open(file_path, 'r') as f:
                        report = json.load(f)
                        report['_file_path'] = file_path
                        report['_file_mtime'] = file_mtime.isoformat()
                        report['_age_hours'] = round(age_hours, 2)
                        reports.append(report)
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: Could not load {file_path}: {e}")
        
        # Sort by timestamp (newest first)
        reports.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return reports
    
    def analyze_trends(self, reports: List[Dict]) -> Dict:
        """Analyze trends across multiple reports"""
        if len(reports) < 2:
            return {
                "status": "insufficient_data",
                "reports_analyzed": len(reports),
                "message": "Need at least 2 reports for trend analysis"
            }
        
        # Extract weakness detection data
        traditional_blocking_data = []
        selective_restrictions_data = []
        timestamps = []
        
        for report in reports:
            timestamp = report.get('timestamp', '')
            if timestamp:
                timestamps.append(timestamp)
            
            # Traditional blocking
            w1 = report.get('results', {}).get('weakness_traditional_blocking', {})
            traditional_blocking_data.append({
                'timestamp': timestamp,
                'detected': w1.get('detected', False),
                'blocking_ratio': w1.get('blocking_ratio', 0.0),
                'blocked_count': w1.get('blocked_count', 0)
            })
            
            # Selective restrictions
            w2 = report.get('results', {}).get('weakness_selective_restrictions', {})
            selective_restrictions_data.append({
                'timestamp': timestamp,
                'detected': w2.get('detected', False),
                'pattern': w2.get('pattern', 'unknown')
            })
        
        # Calculate trends
        trends = {
            "analysis_id": self.analysis_id,
            "timestamp": self.timestamp,
            "reports_analyzed": len(reports),
            "analysis_period_hours": max([r.get('_age_hours', 0) for r in reports]),
            "trends": {}
        }
        
        # Trend 1: Traditional Financial API Blocking
        blocking_ratios = [d['blocking_ratio'] for d in traditional_blocking_data]
        blocking_detections = [d['detected'] for d in traditional_blocking_data]
        
        trends["trends"]["traditional_blocking"] = {
            "current_blocking_ratio": blocking_ratios[0] if blocking_ratios else 0.0,
            "average_blocking_ratio": round(statistics.mean(blocking_ratios), 3) if blocking_ratios else 0.0,
            "max_blocking_ratio": max(blocking_ratios) if blocking_ratios else 0.0,
            "min_blocking_ratio": min(blocking_ratios) if blocking_ratios else 0.0,
            "detection_rate": round(sum(blocking_detections) / len(blocking_detections), 3) if blocking_detections else 0.0,
            "trend_direction": self.calculate_trend_direction(blocking_ratios),
            "status": "ESCALATING" if blocking_ratios and blocking_ratios[0] > statistics.mean(blocking_ratios) * 1.2 else "STABLE",
            "escalation_risk": "HIGH" if blocking_ratios and blocking_ratios[0] >= 0.8 else "MEDIUM" if blocking_ratios and blocking_ratios[0] >= 0.5 else "LOW"
        }
        
        # Trend 2: Selective Service Restrictions
        restriction_detections = [d['detected'] for d in selective_restrictions_data]
        restriction_patterns = [d['pattern'] for d in selective_restrictions_data]
        
        trends["trends"]["selective_restrictions"] = {
            "current_detected": restriction_detections[0] if restriction_detections else False,
            "detection_rate": round(sum(restriction_detections) / len(restriction_detections), 3) if restriction_detections else 0.0,
            "most_common_pattern": max(set(restriction_patterns), key=restriction_patterns.count) if restriction_patterns else "unknown",
            "pattern_stability": len(set(restriction_patterns)) == 1 if restriction_patterns else True,
            "trend_direction": "INCREASING" if restriction_detections and sum(restriction_detections[:3]) > sum(restriction_detections[-3:]) else "STABLE",
            "status": "ACTIVE" if restriction_detections[0] else "INACTIVE",
            "persistence_score": round(sum(restriction_detections) / len(restriction_detections) * 100, 1) if restriction_detections else 0.0
        }
        
        # Combined risk assessment
        combined_risk = self.assess_combined_risk(
            trends["trends"]["traditional_blocking"],
            trends["trends"]["selective_restrictions"]
        )
        
        trends["combined_risk_assessment"] = combined_risk
        
        # Recommendations
        trends["recommendations"] = self.generate_recommendations(trends["trends"])
        
        return trends
    
    def calculate_trend_direction(self, values: List[float]) -> str:
        """Calculate if values are trending up, down, or stable"""
        if len(values) < 3:
            return "INSUFFICIENT_DATA"
        
        # Simple linear trend calculation
        recent = values[:3]
        older = values[-3:] if len(values) >= 6 else values[3:6]
        
        if not recent or not older:
            return "INSUFFICIENT_DATA"
        
        avg_recent = statistics.mean(recent)
        avg_older = statistics.mean(older)
        
        if avg_recent > avg_older * 1.1:
            return "INCREASING"
        elif avg_recent < avg_older * 0.9:
            return "DECREASING"
        else:
            return "STABLE"
    
    def assess_combined_risk(self, blocking_trend: Dict, restrictions_trend: Dict) -> Dict:
        """Assess combined risk from both weaknesses"""
        risk_levels = []
        
        # Traditional blocking risk
        if blocking_trend["escalation_risk"] == "HIGH":
            risk_levels.append("HIGH")
        elif blocking_trend["escalation_risk"] == "MEDIUM":
            risk_levels.append("MEDIUM")
        else:
            risk_levels.append("LOW")
        
        # Selective restrictions risk
        if restrictions_trend["status"] == "ACTIVE" and restrictions_trend["persistence_score"] > 80:
            risk_levels.append("HIGH")
        elif restrictions_trend["status"] == "ACTIVE":
            risk_levels.append("MEDIUM")
        else:
            risk_levels.append("LOW")
        
        # Determine overall risk
        if "HIGH" in risk_levels:
            overall_risk = "HIGH"
        elif "MEDIUM" in risk_levels:
            overall_risk = "MEDIUM"
        else:
            overall_risk = "LOW"
        
        return {
            "overall_risk": overall_risk,
            "traditional_blocking_risk": blocking_trend["escalation_risk"],
            "selective_restrictions_risk": "HIGH" if restrictions_trend["status"] == "ACTIVE" and restrictions_trend["persistence_score"] > 80 else "MEDIUM" if restrictions_trend["status"] == "ACTIVE" else "LOW",
            "risk_factors": [
                f"Traditional blocking ratio: {blocking_trend['current_blocking_ratio']:.1%}",
                f"Selective restrictions active: {restrictions_trend['current_detected']}",
                f"Persistence: {restrictions_trend['persistence_score']}%"
            ]
        }
    
    def generate_recommendations(self, trends: Dict) -> List[str]:
        """Generate recommendations based on trends"""
        recommendations = []
        
        blocking = trends.get("traditional_blocking", {})
        restrictions = trends.get("selective_restrictions", {})
        
        # Traditional blocking recommendations
        if blocking.get("escalation_risk") == "HIGH":
            recommendations.append("🚨 IMMEDIATE ACTION: Traditional financial API blocking has escalated to HIGH risk. Verify network policy immediately.")
        elif blocking.get("escalation_risk") == "MEDIUM":
            recommendations.append("⚠️  Monitor traditional financial API blocking closely. Current blocking ratio indicates MEDIUM risk.")
        
        if blocking.get("trend_direction") == "INCREASING":
            recommendations.append("📈 Traditional blocking is INCREASING. Investigate potential new firewall rules or geographic restrictions.")
        
        # Selective restrictions recommendations
        if restrictions.get("status") == "ACTIVE":
            if restrictions.get("persistence_score", 0) > 90:
                recommendations.append("🔒 Selective restrictions are PERSISTENT ({}%). This indicates stable network policy, not temporary blockage.".format(
                    restrictions.get("persistence_score", 0)
                ))
            
            if not restrictions.get("pattern_stability", True):
                recommendations.append("🔄 Selective restriction patterns are CHANGING. Monitor for new blocking patterns or security policy updates.")
        
        # General recommendations
        if len(recommendations) == 0:
            recommendations.append("✅ All financial weaknesses are at LOW risk and stable. Continue routine monitoring.")
        
        recommendations.append("📊 Review detailed trend analysis in this report for deeper insights.")
        
        return recommendations
    
    def run_analysis(self) -> Dict:
        """Run complete trend analysis"""
        print(f"Starting financial weaknesses trend analysis at {self.timestamp}")
        print(f"Analysis ID: {self.analysis_id}")
        
        # Load reports from last 24 hours
        print("\n1. Loading monitoring reports...")
        reports = self.load_monitoring_reports(hours_back=24)
        print(f"   Loaded {len(reports)} reports from the last 24 hours")
        
        if len(reports) == 0:
            print("   No reports found. Trend analysis requires monitoring data.")
            return {
                "status": "no_data",
                "message": "No monitoring reports found for trend analysis"
            }
        
        # Analyze trends
        print("\n2. Analyzing trends across reports...")
        trends = self.analyze_trends(reports)
        
        # Save analysis
        print("\n3. Saving trend analysis...")
        with open(self.report_file, 'w') as f:
            json.dump(trends, f, indent=2, default=str)
        
        print(f"   Analysis saved to: {self.report_file}")
        
        # Generate summary
        print("\n4. Generating trend summary...")
        summary = self.generate_summary(trends)
        print(summary)
        
        return trends
    
    def generate_summary(self, trends: Dict) -> str:
        """Generate human-readable summary"""
        if trends.get("status") == "no_data":
            return "No trend data available. Run monitoring first."
        
        summary = []
        summary.append("="*70)
        summary.append("FINANCIAL WEAKNESSES TREND ANALYSIS")
        summary.append("="*70)
        summary.append(f"Analysis ID: {trends.get('analysis_id', 'N/A')}")
        summary.append(f"Timestamp: {trends.get('timestamp', 'N/A')}")
        summary.append(f"Reports Analyzed: {trends.get('reports_analyzed', 0)}")
        summary.append(f"Analysis Period: {trends.get('analysis_period_hours', 0)} hours")
        summary.append("")
        
        # Traditional blocking summary
        blocking = trends.get('trends', {}).get('traditional_blocking', {})
        summary.append("TRADITIONAL FINANCIAL API BLOCKING")
        summary.append(f"  Current Blocking Ratio: {blocking.get('current_blocking_ratio', 0):.1%}")
        summary.append(f"  Average Blocking Ratio: {blocking.get('average_blocking_ratio', 0):.1%}")
        summary.append(f"  Trend Direction: {blocking.get('trend_direction', 'UNKNOWN')}")
        summary.append(f"  Status: {blocking.get('status', 'UNKNOWN')}")
        summary.append(f"  Risk Level: {blocking.get('escalation_risk', 'UNKNOWN')}")
        summary.append("")
        
        # Selective restrictions summary
        restrictions = trends.get('trends', {}).get('selective_restrictions', {})
        summary.append("SELECTIVE SERVICE RESTRICTIONS")
        summary.append(f"  Currently Detected: {restrictions.get('current_detected', False)}")
        summary.append(f"  Detection Rate: {restrictions.get('detection_rate', 0):.1%}")
        summary.append(f"  Pattern: {restrictions.get('most_common_pattern', 'UNKNOWN')}")
        summary.append(f"  Persistence: {restrictions.get('persistence_score', 0)}%")
        summary.append(f"  Status: {restrictions.get('status', 'UNKNOWN')}")
        summary.append("")
        
        # Combined risk
        risk = trends.get('combined_risk_assessment', {})
        summary.append("COMBINED RISK ASSESSMENT")
        summary.append(f"  Overall Risk: {risk.get('overall_risk', 'UNKNOWN')}")
        summary.append("  Risk Factors:")
        for factor in risk.get('risk_factors', []):
            summary.append(f"    • {factor}")
        summary.append("")
        
        # Recommendations
        summary.append("RECOMMENDATIONS")
        for i, rec in enumerate(trends.get('recommendations', []), 1):
            summary.append(f"  {i}. {rec}")
        
        summary.append("")
        summary.append(f"Detailed Report: {self.report_file}")
        summary.append("="*70)
        
        return "\n".join(summary)

def main():
    """Main entry point"""
    analyzer = FinancialWeaknessesTrendAnalyzer()
    
    try:
        trends = analyzer.run_analysis()
        
        # Check if immediate action needed
        risk = trends.get('combined_risk_assessment', {}).get('overall_risk', 'LOW')
        if risk == "HIGH":
            print("\n🚨 URGENT: Combined risk assessment is HIGH. Immediate attention required!")
            return 2
        elif risk == "MEDIUM":
            print("\n⚠️  WARNING: Combined risk assessment is MEDIUM. Monitor closely.")
            return 1
        else:
            print("\n✅ NOMINAL: Combined risk assessment is LOW.")
            return 0
    
    except KeyboardInterrupt:
        print("\nTrend analysis interrupted by user")
        return 130
    except Exception as e:
        print(f"Trend analysis failed with error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())