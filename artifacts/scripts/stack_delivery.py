#!/usr/bin/env python3
"""
Stack Delivery System for Subway Lag Failover
Delivers replies from stack with truncation detection and replay capability
"""

import sqlite3
import json
import time
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import hashlib

class StackDelivery:
    """Deliver replies from stack with subway lag handling"""
    
    def __init__(self, db_path: str = "/tmp/reply_stack.db"):
        self.db_path = db_path
        self.truncation_patterns = [
            '...', '[[truncated]]', '[incomplete]', '(cut off)', '[timeout]'
        ]
        
    def detect_truncation(self, content: str, expected_patterns: List[str] = None) -> Tuple[bool, str]:
        """Detect if content appears truncated"""
        if expected_patterns:
            patterns = expected_patterns
        else:
            patterns = self.truncation_patterns
        
        # Check for truncation patterns
        for pattern in patterns:
            if pattern in content:
                return True, f"Truncation pattern detected: {pattern}"
        
        # Check for incomplete sentences at end
        lines = content.strip().split('\n')
        if lines:
            last_line = lines[-1].strip()
            if last_line:
                # Check if ends with complete punctuation
                if last_line[-1] not in ['.', '!', '?', ']', ')', '}', '"', "'"]:
                    # Check for intentional ellipsis
                    if not (last_line.endswith('...') or last_line.endswith('…')):
                        # Check if it looks like a percentage tracking line
                        if not (last_line.startswith('[') and '%' in last_line and ']' in last_line):
                            return True, "Incomplete sentence at end"
        
        # Check for reasonable length (basic heuristic)
        if len(content) < 100 and '%' in content and ']' in content:
            # Might be just a percentage update, not truncated
            pass
        elif len(content) < 50:
            return True, "Very short content, possible truncation"
        
        return False, "No truncation detected"
    
    def simulate_subway_delivery(self, 
                                content: str, 
                                rtt_ms: int = 8000,
                                packet_loss: float = 0.4) -> Tuple[bool, Optional[str], Dict]:
        """Simulate delivery over subway connection"""
        # Simulate latency
        latency = rtt_ms / 2000  # Half round trip for one way
        time.sleep(latency / 1000)  # Convert to seconds
        
        # Simulate packet loss
        if random.random() < packet_loss:
            # Complete loss
            return False, None, {
                'error': 'packet_loss',
                'rtt_ms': rtt_ms,
                'packet_loss': packet_loss,
                'bytes_lost': len(content)
            }
        
        # Simulate possible truncation
        if random.random() < (packet_loss * 2):  # Higher chance of truncation than loss
            # Random truncation point
            if len(content) > 100:
                truncate_at = random.randint(50, len(content) - 50)
                truncated_content = content[:truncate_at] + "... [truncated due to subway lag]"
                
                return True, truncated_content, {
                    'truncated': True,
                    'original_length': len(content),
                    'truncated_length': len(truncated_content),
                    'rtt_ms': rtt_ms,
                    'packet_loss': packet_loss
                }
        
        # Successful delivery
        return True, content, {
            'success': True,
            'bytes_sent': len(content),
            'rtt_ms': rtt_ms,
            'packet_loss': packet_loss
        }
    
    def deliver_next_reply(self, 
                          subway_conditions: Optional[Dict] = None) -> Dict:
        """Deliver the next pending reply from stack"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get next pending reply
        cursor.execute('''
        SELECT id, timestamp, context_json, reply_content, percentage_complete, metadata_json, content_hash
        FROM reply_stack 
        WHERE status = 'pending' 
        ORDER BY timestamp ASC 
        LIMIT 1
        ''')
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {
                'success': False,
                'error': 'no_pending_replies',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        
        reply_id, timestamp, context_json, content, percentage, metadata_json, stored_hash = row
        
        # Verify hash
        current_hash = hashlib.sha256(content.encode()).hexdigest()
        if current_hash != stored_hash:
            conn.close()
            return {
                'success': False,
                'error': 'hash_mismatch',
                'reply_id': reply_id,
                'stored_hash': stored_hash[:16],
                'current_hash': current_hash[:16]
            }
        
        # Mark as delivering
        cursor.execute('UPDATE reply_stack SET status = "delivering" WHERE id = ?', (reply_id,))
        conn.commit()
        
        # Get subway conditions if not provided
        if not subway_conditions:
            cursor.execute('''
            SELECT rtt_ms, packet_loss 
            FROM subway_connectivity 
            ORDER BY timestamp DESC 
            LIMIT 1
            ''')
            subway_row = cursor.fetchone()
            if subway_row:
                subway_conditions = {
                    'rtt_ms': subway_row[0] or 8000,
                    'packet_loss': subway_row[1] or 0.4
                }
            else:
                subway_conditions = {'rtt_ms': 8000, 'packet_loss': 0.4}
        
        # Simulate delivery over subway
        success, delivered_content, delivery_stats = self.simulate_subway_delivery(
            content,
            rtt_ms=subway_conditions.get('rtt_ms', 8000),
            packet_loss=subway_conditions.get('packet_loss', 0.4)
        )
        
        # Check for truncation in delivered content
        truncation_detected = False
        truncation_reason = None
        
        if success and delivered_content:
            truncation_detected, truncation_reason = self.detect_truncation(delivered_content)
        
        # Update stack based on delivery result
        if success:
            if truncation_detected:
                # Delivered but truncated - mark for replay
                cursor.execute('''
                UPDATE reply_stack 
                SET status = 'pending', 
                    truncated_detected = TRUE,
                    replay_count = replay_count + 1
                WHERE id = ?
                ''', (reply_id,))
                status = 'delivered_truncated'
            else:
                # Successfully delivered
                cursor.execute('''
                UPDATE reply_stack 
                SET status = 'delivered', 
                    delivered_at = ?
                WHERE id = ?
                ''', (datetime.now(timezone.utc).isoformat(), reply_id))
                status = 'delivered'
        else:
            # Delivery failed
            cursor.execute('''
            UPDATE reply_stack 
            SET status = 'failed'
            WHERE id = ?
            ''', (reply_id,))
            status = 'failed'
        
        # Log delivery attempt
        cursor.execute('''
        INSERT INTO delivery_log 
        (stack_id, attempt_timestamp, success, truncation_detected, bytes_sent, error_message)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            reply_id,
            datetime.now(timezone.utc).isoformat(),
            success,
            truncation_detected,
            len(content) if success and delivered_content else 0,
            delivery_stats.get('error') if not success else None
        ))
        
        conn.commit()
        conn.close()
        
        # Prepare result
        result = {
            'success': success,
            'reply_id': reply_id,
            'status': status,
            'original_content_length': len(content),
            'delivered_content_length': len(delivered_content) if delivered_content else 0,
            'percentage_complete': percentage,
            'truncation_detected': truncation_detected,
            'truncation_reason': truncation_reason,
            'delivery_stats': delivery_stats,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'needs_replay': truncation_detected or not success
        }
        
        if delivered_content and len(delivered_content) < 200:
            result['delivered_preview'] = delivered_content
        elif delivered_content:
            result['delivered_preview'] = delivered_content[:100] + '...' + delivered_content[-100:] if len(delivered_content) > 200 else delivered_content
        
        return result
    
    def replay_truncated_replies(self, max_replays: int = 3) -> List[Dict]:
        """Replay truncated replies"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get truncated replies
        cursor.execute('''
        SELECT id, reply_content, replay_count
        FROM reply_stack 
        WHERE truncated_detected = TRUE 
          AND status = 'pending'
          AND replay_count < ?
        ORDER BY timestamp ASC
        ''', (max_replays,))
        
        replay_results = []
        for row in cursor.fetchall():
            reply_id, content, replay_count = row
            
            # Mark as delivering
            cursor.execute('UPDATE reply_stack SET status = "delivering" WHERE id = ?', (reply_id,))
            conn.commit()
            
            # Simulate re-delivery (with potentially better conditions)
            success, delivered_content, delivery_stats = self.simulate_subway_delivery(
                content,
                rtt_ms=4000,  # Better RTT for replay
                packet_loss=0.2  # Better packet loss for replay
            )
            
            # Check for truncation again
            truncation_detected, truncation_reason = self.detect_truncation(
                delivered_content if delivered_content else ""
            )
            
            # Update based on replay result
            if success and not truncation_detected:
                cursor.execute('''
                UPDATE reply_stack 
                SET status = 'delivered', 
                    delivered_at = ?,
                    truncated_detected = FALSE
                WHERE id = ?
                ''', (datetime.now(timezone.utc).isoformat(), reply_id))
                replay_status = 'replay_success'
            else:
                cursor.execute('''
                UPDATE reply_stack 
                SET status = 'pending',
                    replay_count = replay_count + 1
                WHERE id = ?
                ''', (reply_id,))
                replay_status = 'replay_failed'
            
            # Log replay attempt
            cursor.execute('''
            INSERT INTO delivery_log 
            (stack_id, attempt_timestamp, success, truncation_detected, bytes_sent, error_message, operation_note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                reply_id,
                datetime.now(timezone.utc).isoformat(),
                success and not truncation_detected,
                truncation_detected,
                len(delivered_content) if delivered_content else 0,
                delivery_stats.get('error') if not success else None,
                f'replay_attempt_{replay_count + 1}'
            ))
            
            replay_results.append({
                'reply_id': reply_id,
                'status': replay_status,
                'success': success and not truncation_detected,
                'truncation_detected': truncation_detected,
                'replay_count': replay_count + 1,
                'delivery_stats': delivery_stats
            })
        
        conn.commit()
        conn.close()
        
        return replay_results
    
    def deliver_all_pending(self, 
                           max_attempts: int = 3,
                           delay_between_ms: int = 1000) -> Dict:
        """Attempt to deliver all pending replies"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get count of pending replies
        cursor.execute('SELECT COUNT(*) FROM reply_stack WHERE status = "pending"')
        total_pending = cursor.fetchone()[0]
        
        if total_pending == 0:
            conn.close()
            return {
                'success': True,
                'message': 'no_pending_replies',
                'total_pending': 0,
                'delivered': 0,
                'failed': 0,
                'truncated': 0
            }
        
        results = []
        attempts = 0
        
        while attempts < max_attempts and total_pending > 0:
            attempts += 1
            
            # Try to deliver one reply
            delivery_result = self.deliver_next_reply()
            results.append(delivery_result)
            
            if delivery_result.get('success') and not delivery_result.get('truncation_detected'):
                # Successfully delivered, not truncated
                pass
            elif delivery_result.get('truncation_detected'):
                # Delivered but truncated - will be retried if within replay limits
                pass
            else:
                # Failed delivery
                pass
            
            # Check current pending count
            cursor.execute('SELECT COUNT(*) FROM reply_stack WHERE status = "pending"')
            total_pending = cursor.fetchone()[0]
            
            # Delay between attempts if more remain
            if total_pending > 0 and attempts < max_attempts:
                time.sleep(delay_between_ms / 1000)
        
        conn.close()
        
        # Analyze results
        delivered = sum(1 for r in results if r.get('success') and not r.get('truncation_detected'))
        truncated = sum(1 for r in results if r.get('truncation_detected'))
        failed = sum(1 for r in results if not r.get('success'))
        
        return {
            'success': delivered > 0 or truncated > 0,
            'total_attempts': attempts,
            'total_pending_initial': total_pending + delivered + truncated + failed,
            'delivered': delivered,
            'truncated': truncated,
            'failed': failed,
            'still_pending': total_pending,
            'results': results
        }
    
    def get_delivery_metrics(self, hours: int = 24) -> Dict:
        """Get delivery metrics for specified time period"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Delivery success rate
        cursor.execute('''
        SELECT 
            COUNT(*) as total_attempts,
            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN truncation_detected = TRUE THEN 1 ELSE 0 END) as truncated,
            AVG(bytes_sent) as avg_bytes
        FROM delivery_log
        WHERE datetime(attempt_timestamp) > datetime('now', ?)
        ''', (f'-{hours} hours',))
        
        delivery_row = cursor.fetchone()
        delivery_metrics = {
            'total_attempts': delivery_row[0] or 0,
            'successful': delivery_row[1] or 0,
            'truncated': delivery_row[2] or 0,
            'avg_bytes': delivery_row[3] or 0,
            'success_rate': (delivery_row[1] or 0) / (delivery_row[0] or 1) * 100 if delivery_row[0] else 0,
            'truncation_rate': (delivery_row[2] or 0) / (delivery_row[0] or 1) * 100 if delivery_row[0] else 0
        }
        
        # Stack status
        cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
            SUM(CASE WHEN truncated_detected = TRUE THEN 1 ELSE 0 END) as truncated
        FROM reply_stack
        WHERE datetime(timestamp) > datetime('now', ?)
        ''', (f'-{hours} hours',))
        
        stack_row = cursor.fetchone()
        stack_metrics = {
            'total': stack_row[0] or 0,
            'pending': stack_row[1] or 0,
            'delivered': stack_row[2] or 0,
            'truncated': stack_row[3] or 0,
            'delivery_rate': (stack_row[2] or 0) / (stack_row[0] or 1) * 100 if stack_row[0] else 0
        }
        
        # Subway conditions
        cursor.execute('''
        SELECT 
            AVG(rtt_ms) as avg_rtt,
            AVG(packet_loss) as avg_loss,
            COUNT(*) as samples
        FROM subway_connectivity
        WHERE datetime(timestamp) > datetime('now', ?)
        ''', (f'-{hours} hours',))
        
        subway_row = cursor.fetchone()
        subway_metrics = {
            'avg_rtt_ms': subway_row[0] or 0,
            'avg_packet_loss': subway_row[1] or 0,
            'samples': subway_row[2] or 0
        }
        
        conn.close()
        
        return {
            'time_period_hours': hours,
            'delivery': delivery_metrics,
            'stack': stack_metrics,
            'subway': subway_metrics,
            'overall_health': self._calculate_overall_health(
                delivery_metrics, stack_metrics, subway_metrics
            )
        }
    
    def _calculate_overall_health(self, delivery: Dict, stack: Dict, subway: Dict) -> str:
        """Calculate overall system health"""
        issues = []
        
        if delivery['success_rate'] < 50:
            issues.append(f'Low delivery success: {delivery["success_rate"]:.1f}%')
        
        if delivery['truncation_rate'] > 30:
            issues.append(f'High truncation rate: {delivery["truncation_rate"]:.1f}%')
        
        if stack['pending'] > 10:
            issues.append(f'High pending count: {stack["pending"]}')
        
        if subway['avg_rtt_ms'] > 5000:
            issues.append(f'High subway latency: {subway["avg_rtt_ms"]:.0f}ms')
        
        if subway['avg_packet_loss'] > 0.3:
            issues.append(f'High packet loss: {subway["avg_packet_loss"]:.1%}')
        
        if not issues:
            return 'healthy'
        elif len(issues) <= 2:
            return 'degraded'
        else:
            return 'unhealthy'

if __name__ == "__main__":
    delivery = StackDelivery()
    
    # Get current metrics
    metrics = delivery.get_delivery_metrics(hours=1)
    print("=== DELIVERY METRICS (Last Hour) ===")
    print(f"Success rate: {metrics['delivery']['success_rate']:.1f}%")
    print(f"Truncation rate: {metrics['delivery']['truncation_rate']:.1f}%")
    print(f"Pending replies: {metrics['stack']['pending']}")
    print(f"Subway latency: {metrics['subway']['avg_rtt_ms']:.0f}ms")
    print(f"Overall health: {metrics['overall_health'].upper()}")
    
    # Try to deliver one reply
    print("\n=== ATTEMPTING DELIVERY ===")
    result = delivery.deliver_next_reply()
    print(f"Result: {result['status']}")
    if result.get('truncation_detected'):
        print(f"Truncation reason: {result.get('truncation_reason')}")
    print(f"Content length: {result.get('delivered_content_length')} bytes")
    
    # Check for truncated replies to replay
    print("\n=== CHECKING FOR REPLAYS ===")
    replay_results = delivery.replay_truncated_replies(max_replays=2)
    if replay_results:
        print(f"Replayed {len(replay_results)} truncated replies")
        for replay in replay_results:
            print(f"  ID {replay['reply_id']}: {replay['status']}")
    else:
        print("No truncated replies need replay")