#!/usr/bin/env python3
"""
Stack Monitor for Subway Lag Failover
Monitors reply stack status and handles truncation detection
"""

import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List
import time

class StackMonitor:
    """Monitor and manage the reply stack"""
    
    def __init__(self, db_path: str = "/tmp/reply_stack.db"):
        self.db_path = db_path
    
    def get_status(self) -> Dict:
        """Get comprehensive stack status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Stack summary
        cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'delivering' THEN 1 ELSE 0 END) as delivering,
            SUM(CASE WHEN truncated_detected = TRUE THEN 1 ELSE 0 END) as truncated,
            AVG(percentage_complete) as avg_percentage,
            MAX(timestamp) as latest,
            MIN(timestamp) as earliest
        FROM reply_stack
        ''')
        
        summary_row = cursor.fetchone()
        summary = {
            'total': summary_row[0] or 0,
            'pending': summary_row[1] or 0,
            'delivered': summary_row[2] or 0,
            'failed': summary_row[3] or 0,
            'delivering': summary_row[4] or 0,
            'truncated': summary_row[5] or 0,
            'avg_percentage': summary_row[6] or 0,
            'latest': summary_row[7],
            'earliest': summary_row[8]
        }
        
        # Subway conditions
        cursor.execute('''
        SELECT 
            COUNT(*) as total_events,
            SUM(CASE WHEN lag_detected = TRUE THEN 1 ELSE 0 END) as lag_events,
            SUM(CASE WHEN truncation_detected = TRUE THEN 1 ELSE 0 END) as truncation_events,
            AVG(rtt_ms) as avg_rtt,
            AVG(packet_loss) as avg_packet_loss,
            MAX(timestamp) as latest_event
        FROM subway_connectivity
        ''')
        
        subway_row = cursor.fetchone()
        subway = {
            'total_events': subway_row[0] or 0,
            'lag_events': subway_row[1] or 0,
            'truncation_events': subway_row[2] or 0,
            'avg_rtt_ms': subway_row[3] or 0,
            'avg_packet_loss': subway_row[4] or 0,
            'latest_event': subway_row[5]
        }
        
        # Delivery log summary
        cursor.execute('''
        SELECT 
            COUNT(*) as total_attempts,
            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN truncation_detected = TRUE THEN 1 ELSE 0 END) as truncated,
            AVG(bytes_sent) as avg_bytes_sent
        FROM delivery_log
        ''')
        
        delivery_row = cursor.fetchone()
        delivery = {
            'total_attempts': delivery_row[0] or 0,
            'successful': delivery_row[1] or 0,
            'truncated': delivery_row[2] or 0,
            'avg_bytes_sent': delivery_row[3] or 0
        }
        
        # Pending replies details
        cursor.execute('''
        SELECT id, timestamp, percentage_complete, LENGTH(reply_content) as length
        FROM reply_stack 
        WHERE status = 'pending'
        ORDER BY timestamp DESC
        LIMIT 5
        ''')
        
        pending = []
        for row in cursor.fetchall():
            pending.append({
                'id': row[0],
                'timestamp': row[1],
                'percentage_complete': row[2],
                'length_bytes': row[3]
            })
        
        # Recent subway events
        cursor.execute('''
        SELECT timestamp, condition, rtt_ms, packet_loss
        FROM subway_connectivity
        ORDER BY timestamp DESC
        LIMIT 3
        ''')
        
        recent_events = []
        for row in cursor.fetchall():
            recent_events.append({
                'timestamp': row[0],
                'condition': row[1],
                'rtt_ms': row[2],
                'packet_loss': row[3]
            })
        
        conn.close()
        
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'summary': summary,
            'subway_conditions': subway,
            'delivery_stats': delivery,
            'pending_replies': pending,
            'recent_subway_events': recent_events,
            'health_status': self._calculate_health(summary, subway)
        }
    
    def _calculate_health(self, summary: Dict, subway: Dict) -> Dict:
        """Calculate stack health status"""
        health = {
            'overall': 'healthy',
            'issues': [],
            'recommendations': []
        }
        
        # Check for high pending count
        if summary['pending'] > 10:
            health['overall'] = 'warning'
            health['issues'].append(f'High pending count: {summary["pending"]}')
            health['recommendations'].append('Consider increasing delivery attempts')
        
        # Check for high failure rate
        if summary['failed'] > 0 and summary['total'] > 0:
            failure_rate = summary['failed'] / summary['total']
            if failure_rate > 0.1:  # 10% failure rate
                health['overall'] = 'warning'
                health['issues'].append(f'High failure rate: {failure_rate:.1%}')
                health['recommendations'].append('Investigate delivery failures')
        
        # Check subway conditions
        if subway['avg_rtt_ms'] > 5000:  # 5 seconds
            health['issues'].append(f'High subway latency: {subway["avg_rtt_ms"]:.0f}ms')
            health['recommendations'].append('Expect truncation, use stack replay')
        
        if subway['avg_packet_loss'] > 0.3:  # 30% packet loss
            health['issues'].append(f'High packet loss: {subway["avg_packet_loss"]:.1%}')
            health['recommendations'].append('Enable aggressive replay strategy')
        
        if health['issues'] and health['overall'] == 'healthy':
            health['overall'] = 'degraded'
        
        return health
    
    def get_replay_candidates(self) -> List[Dict]:
        """Get replies that should be replayed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get truncated or failed replies from last hour
        cursor.execute('''
        SELECT id, timestamp, context_json, reply_content, percentage_complete, truncated_detected, status
        FROM reply_stack 
        WHERE (truncated_detected = TRUE OR status = 'failed')
          AND datetime(timestamp) > datetime('now', '-1 hour')
        ORDER BY timestamp DESC
        ''')
        
        candidates = []
        for row in cursor.fetchall():
            reply_id, timestamp, context_json, content, percentage, truncated, status = row
            candidates.append({
                'id': reply_id,
                'timestamp': timestamp,
                'context': json.loads(context_json),
                'content': content[:100] + '...' if len(content) > 100 else content,
                'percentage_complete': percentage,
                'truncated': bool(truncated),
                'status': status,
                'priority': self._calculate_priority(percentage, truncated, status)
            })
        
        conn.close()
        return candidates
    
    def _calculate_priority(self, percentage: int, truncated: bool, status: str) -> int:
        """Calculate replay priority (higher = more urgent)"""
        priority = 0
        
        if truncated:
            priority += 50  # Truncated replies are high priority
        
        if status == 'failed':
            priority += 30  # Failed deliveries need retry
        
        if percentage < 10:
            priority += 20  # Early percentage replies are important
        
        if percentage > 90:
            priority += 10  # Completion replies are important
        
        return priority
    
    def cleanup_old_entries(self, max_age_hours: int = 24):
        """Clean up old stack entries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delete delivered, non-truncated entries older than max_age_hours
        cursor.execute('''
        DELETE FROM reply_stack 
        WHERE status = 'delivered'
          AND truncated_detected = FALSE
          AND datetime(timestamp) < datetime('now', ?)
        ''', (f'-{max_age_hours} hours',))
        
        deleted_replies = cursor.rowcount
        
        # Delete old subway connectivity logs
        cursor.execute('''
        DELETE FROM subway_connectivity
        WHERE datetime(timestamp) < datetime('now', ?)
        ''', (f'-{max_age_hours * 2} hours',))
        
        deleted_events = cursor.rowcount
        
        # Delete old delivery logs
        cursor.execute('''
        DELETE FROM delivery_log
        WHERE datetime(attempt_timestamp) < datetime('now', ?)
        ''', (f'-{max_age_hours * 2} hours',))
        
        deleted_logs = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return {
            'deleted_replies': deleted_replies,
            'deleted_events': deleted_events,
            'deleted_logs': deleted_logs,
            'total_deleted': deleted_replies + deleted_events + deleted_logs
        }
    
    def simulate_truncation_detection(self, reply_id: int) -> bool:
        """Simulate truncation detection for testing"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Mark as truncated
        cursor.execute('''
        UPDATE reply_stack 
        SET truncated_detected = TRUE,
            status = 'pending'  # Set back to pending for replay
        WHERE id = ?
        ''', (reply_id,))
        
        # Log the truncation detection
        cursor.execute('''
        INSERT INTO delivery_log 
        (stack_id, attempt_timestamp, success, truncation_detected, error_message)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            reply_id,
            datetime.now(timezone.utc).isoformat(),
            False,
            True,
            'Simulated truncation detection for testing'
        ))
        
        conn.commit()
        conn.close()
        
        return True
    
    def continuous_monitor(self, interval_seconds: int = 30):
        """Continuous monitoring loop"""
        print(f"Starting continuous stack monitor (interval: {interval_seconds}s)")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                status = self.get_status()
                
                print(f"\n=== STACK MONITOR {datetime.now().strftime('%H:%M:%S')} ===")
                print(f"Total replies: {status['summary']['total']}")
                print(f"Pending: {status['summary']['pending']}")
                print(f"Delivered: {status['summary']['delivered']}")
                print(f"Truncated: {status['summary']['truncated']}")
                print(f"Health: {status['health_status']['overall'].upper()}")
                
                if status['health_status']['issues']:
                    print("Issues detected:")
                    for issue in status['health_status']['issues']:
                        print(f"  - {issue}")
                
                if status['pending_replies']:
                    print(f"\nRecent pending replies:")
                    for pending in status['pending_replies'][:3]:
                        print(f"  ID {pending['id']}: {pending['percentage_complete']}% complete ({pending['length_bytes']} bytes)")
                
                # Check for replay candidates
                candidates = self.get_replay_candidates()
                if candidates:
                    print(f"\nReplay candidates: {len(candidates)}")
                    for candidate in candidates[:2]:
                        print(f"  ID {candidate['id']}: {candidate['status']} (priority: {candidate['priority']})")
                
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print("\nMonitor stopped by user")
    
    def generate_report(self) -> Dict:
        """Generate detailed stack report"""
        status = self.get_status()
        candidates = self.get_replay_candidates()
        
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'monitor_version': '1.0',
            'status_summary': status,
            'replay_candidates': candidates,
            'recommendations': []
        }
        
        # Generate recommendations
        if status['summary']['pending'] > 5:
            report['recommendations'].append({
                'action': 'process_pending',
                'priority': 'high',
                'reason': f'{status["summary"]["pending"]} replies pending delivery'
            })
        
        if candidates:
            report['recommendations'].append({
                'action': 'replay_truncated',
                'priority': 'medium',
                'reason': f'{len(candidates)} replies need replay due to truncation/failure'
            })
        
        if status['subway_conditions']['avg_rtt_ms'] > 3000:
            report['recommendations'].append({
                'action': 'enable_aggressive_replay',
                'priority': 'medium',
                'reason': f'High subway latency: {status["subway_conditions"]["avg_rtt_ms"]:.0f}ms'
            })
        
        return report

if __name__ == "__main__":
    monitor = StackMonitor()
    
    # Get current status
    status = monitor.get_status()
    print(json.dumps(status, indent=2))
    
    # Check for replay candidates
    candidates = monitor.get_replay_candidates()
    if candidates:
        print(f"\nFound {len(candidates)} replay candidates:")
        for candidate in candidates:
            print(f"  ID {candidate['id']}: {candidate['status']} (priority: {candidate['priority']})")
    
    # Generate report
    report = monitor.generate_report()
    print(f"\nGenerated report with {len(report['recommendations'])} recommendations")