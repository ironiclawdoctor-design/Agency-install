#!/usr/bin/env python3
"""
Financial Weaknesses Monitor
Monitors top 2 external financial weaknesses:
1. Traditional Financial API Blocking
2. Selective Service Restrictions
"""

import json
import subprocess
import time
import sys
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import urllib.request
import urllib.error
import socket

class FinancialWeaknessesMonitor:
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.monitoring_id = f"FWM-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self.log_dir = "/root/.openclaw/workspace/monitoring"
        os.makedirs(self.log_dir, exist_ok=True)
        self.report_file = os.path.join(
            self.log_dir, 
            f"financial-weaknesses-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.json"
        )
        
        # Top 2 weaknesses to monitor
        self.weaknesses = [
            "traditional_financial_api_blocking",
            "selective_service_restrictions"
        ]
        
        # API endpoints to test
        self.apis = {
            # Working APIs (should be accessible)
            "coingecko": {
                "url": "https://api.coingecko.com/api/v3/ping",
                "expected_pattern": "gecko_says",
                "category": "crypto"
            },
            "exchangerate": {
                "url": "https://api.exchangerate-api.com/v4/latest/USD",
                "expected_pattern": "rates",
                "category": "general"
            },
            "bloomberg": {
                "url": "https://www.bloomberg.com/markets",
                "expected_pattern": "<!DOCTYPE",
                "category": "general_finance"
            },
            
            # Traditional financial APIs (likely blocked)
            "yahoo_finance": {
                "url": "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC",
                "expected_pattern": "regularMarketPrice",
                "category": "traditional_finance"
            },
            "coincap": {
                "url": "https://api.coincap.io/v2/assets/bitcoin",
                "expected_pattern": "priceUsd",
                "category": "crypto_finance"
            },
            "nasdaq": {
                "url": "https://www.nasdaq.com",
                "expected_pattern": "<!DOCTYPE",
                "category": "traditional_finance"
            }
        }
        
        self.results = {
            "monitoring_id": self.monitoring_id,
            "timestamp": self.timestamp,
            "weaknesses_monitored": self.weaknesses,
            "results": {}
        }
    
    def test_api(self, name: str, api_info: Dict) -> Dict:
        """Test a single API endpoint"""
        url = api_info["url"]
        expected_pattern = api_info["expected_pattern"]
        category = api_info["category"]
        
        start_time = time.time()
        result = {
            "api": name,
            "category": category,
            "url": url,
            "start_time": start_time
        }
        
        try:
            # Set timeout for the request
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'FinancialWeaknessesMonitor/1.0'}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                response_data = response.read().decode('utf-8', errors='ignore')
                duration = time.time() - start_time
                
                if expected_pattern in response_data:
                    result.update({
                        "status": "working",
                        "duration_seconds": round(duration, 3),
                        "response_preview": response_data[:100] if response_data else "",
                        "http_status": response.getcode()
                    })
                else:
                    result.update({
                        "status": "unexpected_response",
                        "duration_seconds": round(duration, 3),
                        "response_preview": response_data[:100] if response_data else "",
                        "http_status": response.getcode(),
                        "pattern_matched": False
                    })
        
        except urllib.error.HTTPError as e:
            result.update({
                "status": "http_error",
                "duration_seconds": round(time.time() - start_time, 3),
                "http_status": e.code,
                "error": str(e)
            })
        except urllib.error.URLError as e:
            result.update({
                "status": "connection_error",
                "duration_seconds": round(time.time() - start_time, 3),
                "error": str(e.reason) if hasattr(e, 'reason') else str(e)
            })
        except socket.timeout:
            result.update({
                "status": "timeout",
                "duration_seconds": 10.0,
                "error": "Connection timeout after 10 seconds"
            })
        except Exception as e:
            result.update({
                "status": "error",
                "duration_seconds": round(time.time() - start_time, 3),
                "error": str(e)
            })
        
        return result
    
    def test_basic_connectivity(self) -> Dict:
        """Test basic internet connectivity"""
        result = {"test": "basic_connectivity"}
        
        try:
            # Test ping to Google DNS
            ping_result = subprocess.run(
                ["ping", "-c", "2", "-W", "2", "8.8.8.8"],
                capture_output=True,
                text=True
            )
            
            if ping_result.returncode == 0:
                result.update({
                    "status": "working",
                    "details": "basic_internet_connectivity_ok",
                    "output": ping_result.stdout.strip()[:100]
                })
            else:
                result.update({
                    "status": "blocked",
                    "details": "basic_internet_connectivity_failed",
                    "output": ping_result.stderr.strip()[:100]
                })
        
        except Exception as e:
            result.update({
                "status": "error",
                "details": "connectivity_test_failed",
                "error": str(e)
            })
        
        return result
    
    def analyze_traditional_financial_blocking(self, api_results: List[Dict]) -> Dict:
        """Analyze traditional financial API blocking pattern"""
        traditional_apis = [r for r in api_results if r["category"] == "traditional_finance"]
        total_tests = len(traditional_apis)
        
        if total_tests == 0:
            return {
                "weakness": "traditional_financial_api_blocking",
                "detected": False,
                "reason": "no_traditional_finance_apis_tested"
            }
        
        blocked_count = sum(1 for r in traditional_apis if r["status"] in ["blocked", "timeout", "connection_error", "http_error"])
        blocking_ratio = blocked_count / total_tests
        
        analysis = {
            "weakness": "traditional_financial_api_blocking",
            "detected": blocking_ratio >= 0.66,
            "blocking_ratio": round(blocking_ratio, 3),
            "blocked_count": blocked_count,
            "total_tests": total_tests,
            "blocked_apis": [
                r["api"] for r in traditional_apis 
                if r["status"] in ["blocked", "timeout", "connection_error", "http_error"]
            ]
        }
        
        return analysis
    
    def analyze_selective_restrictions(self, api_results: List[Dict]) -> Dict:
        """Analyze selective service restrictions pattern"""
        # Group by category
        crypto_working = any(
            r["status"] == "working" and r["category"] == "crypto" 
            for r in api_results
        )
        
        general_working = any(
            r["status"] == "working" and r["category"] in ["general", "general_finance"]
            for r in api_results
        )
        
        traditional_blocked = any(
            r["status"] in ["blocked", "timeout", "connection_error", "http_error"] 
            and r["category"] == "traditional_finance"
            for r in api_results
        )
        
        crypto_finance_blocked = any(
            r["status"] in ["blocked", "timeout", "connection_error", "http_error"] 
            and r["category"] == "crypto_finance"
            for r in api_results
        )
        
        # Pattern: Basic internet works, but traditional financial APIs are blocked
        analysis = {
            "weakness": "selective_service_restrictions",
            "crypto_accessible": crypto_working,
            "general_web_accessible": general_working,
            "traditional_finance_blocked": traditional_blocked,
            "crypto_finance_blocked": crypto_finance_blocked
        }
        
        # Detection logic
        if (crypto_working or general_working) and (traditional_blocked or crypto_finance_blocked):
            analysis["detected"] = True
            analysis["pattern"] = "selective_blocking_detected"
        else:
            analysis["detected"] = False
            analysis["pattern"] = "no_clear_selective_blocking"
        
        return analysis
    
    def run_monitoring(self) -> Tuple[bool, Dict]:
        """Run complete monitoring cycle"""
        print(f"Starting financial weaknesses monitoring at {self.timestamp}")
        print(f"Monitoring ID: {self.monitoring_id}")
        print(f"Report file: {self.report_file}")
        
        # Test basic connectivity
        print("\n1. Testing basic internet connectivity...")
        connectivity_result = self.test_basic_connectivity()
        self.results["results"]["basic_connectivity"] = connectivity_result
        print(f"   Status: {connectivity_result.get('status', 'unknown')}")
        
        # Test all APIs
        print("\n2. Testing financial APIs...")
        api_results = []
        for name, api_info in self.apis.items():
            print(f"   Testing {name}...", end=" ")
            result = self.test_api(name, api_info)
            api_results.append(result)
            print(f"{result['status']}")
        
        self.results["results"]["api_tests"] = api_results
        
        # Analyze weaknesses
        print("\n3. Analyzing financial weaknesses...")
        
        # Weakness 1: Traditional Financial API Blocking
        weakness1 = self.analyze_traditional_financial_blocking(api_results)
        self.results["results"]["weakness_traditional_blocking"] = weakness1
        print(f"   Traditional Financial API Blocking: {'DETECTED' if weakness1['detected'] else 'NOT DETECTED'}")
        
        # Weakness 2: Selective Service Restrictions
        weakness2 = self.analyze_selective_restrictions(api_results)
        self.results["results"]["weakness_selective_restrictions"] = weakness2
        print(f"   Selective Service Restrictions: {'DETECTED' if weakness2['detected'] else 'NOT DETECTED'}")
        
        # Save report
        print(f"\n4. Saving monitoring report...")
        with open(self.report_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print(f"   Report saved to: {self.report_file}")
        
        # Determine if anomalies detected
        anomalies_detected = weakness1["detected"] or weakness2["detected"]
        
        if anomalies_detected:
            print(f"\n⚠️  ANOMALY DETECTED: Financial weaknesses confirmed")
            print(f"   - Traditional blocking: {weakness1['detected']}")
            print(f"   - Selective restrictions: {weakness2['detected']}")
        else:
            print(f"\n✅ STATUS NOMINAL: No financial weaknesses detected")
        
        return anomalies_detected, self.results
    
    def generate_summary(self) -> str:
        """Generate a human-readable summary"""
        if not self.results.get("results"):
            return "No monitoring results available"
        
        summary = []
        summary.append(f"Financial Weaknesses Monitoring Summary")
        summary.append(f"Monitoring ID: {self.monitoring_id}")
        summary.append(f"Timestamp: {self.timestamp}")
        summary.append("")
        
        # Basic connectivity
        conn = self.results["results"].get("basic_connectivity", {})
        summary.append(f"Basic Connectivity: {conn.get('status', 'unknown')}")
        
        # Weakness 1
        w1 = self.results["results"].get("weakness_traditional_blocking", {})
        summary.append(f"Traditional Financial API Blocking: {'DETECTED' if w1.get('detected') else 'NOT DETECTED'}")
        if w1.get('detected'):
            summary.append(f"  Blocked APIs: {', '.join(w1.get('blocked_apis', []))}")
        
        # Weakness 2
        w2 = self.results["results"].get("weakness_selective_restrictions", {})
        summary.append(f"Selective Service Restrictions: {'DETECTED' if w2.get('detected') else 'NOT DETECTED'}")
        
        # Overall status
        anomalies = w1.get('detected', False) or w2.get('detected', False)
        summary.append("")
        summary.append(f"Overall Status: {'ANOMALY DETECTED' if anomalies else 'NOMINAL'}")
        summary.append(f"Report: {self.report_file}")
        
        return "\n".join(summary)

def main():
    """Main entry point"""
    monitor = FinancialWeaknessesMonitor()
    
    try:
        anomalies_detected, results = monitor.run_monitoring()
        
        # Print summary
        print("\n" + "="*60)
        print(monitor.generate_summary())
        print("="*60)
        
        # Exit with appropriate code
        sys.exit(1 if anomalies_detected else 0)
    
    except KeyboardInterrupt:
        print("\nMonitoring interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Monitoring failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()