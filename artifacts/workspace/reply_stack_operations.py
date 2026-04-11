#!/usr/bin/env python3
"""
Reply Stack Operations for Subway Lag Failover
Records all intended replies in stack structure for replay when truncation detected
"""

import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import hashlib

class ReplyStack:
    """Stack-based reply recording for subway lag failover"""
    
    def __init__(self, db_path: str = "/tmp/reply_stack.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.create_tables()
    
    def create_tables(self):
        """Ensure tables exist"""
        cursor = self.conn.cursor()
        
        # Main stack table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reply_stack (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            context_json TEXT NOT NULL,
            reply_content TEXT NOT NULL,
            percentage_complete INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            delivered_at TEXT,
            truncated_detected BOOLEAN DEFAULT FALSE,
            metadata_json TEXT,
            content_hash TEXT,
            replay_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Delivery log
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS delivery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stack_id INTEGER,
            attempt_timestamp TEXT,
            success BOOLEAN,
            truncation_detected BOOLEAN,
            bytes_sent INTEGER,
            bytes_received INTEGER,
            error_message TEXT,
            network_conditions TEXT,
            FOREIGN KEY (stack_id) REFERENCES reply_stack(id)
        )
        ''')
        
        # Subway connectivity log
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS subway_connectivity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            condition TEXT,
            lag_detected BOOLEAN,
            truncation_detected BOOLEAN,
            rtt_ms INTEGER,
            packet_loss REAL,
            location_json TEXT
        )
        ''')
        
        self.conn.commit()
    
    def record_subway_condition(self, 
                               condition: str = "lag_detected",
                               lag_detected: bool = True,
                               truncation_detected: bool = False,
                               rtt_ms: Optional[int] = None,
                               packet_loss: Optional[float] = None,
                               location: Optional[Dict] = None):
        """Record subway connectivity conditions"""
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT INTO subway_connectivity 
        (timestamp, condition, lag_detected, truncation_detected, rtt_ms, packet_loss, location_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now(timezone.utc).isoformat(),
            condition,
            lag_detected,
            truncation_detected,
            rtt_ms,
            packet_loss,
            json.dumps(location) if location else None
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def push_reply(self, 
                   reply_content: str,
                   context: Dict,
                   percentage_complete: int = 0,
                   metadata: Optional[Dict] = None) -> int:
        """Push a reply onto the stack"""
        content_hash = hashlib.sha256(reply_content.encode()).hexdigest()
        
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT INTO reply_stack 
        (timestamp, context_json, reply_content, percentage_complete, status, metadata_json, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now(timezone.utc).isoformat(),
            json.dumps(context),
            reply_content,
            percentage_complete,
            'pending',
            json.dumps(metadata) if metadata else None,
            content_hash
        ))
        self.conn.commit()
        stack_id = cursor.lastrowid
        
        # Log the push operation
        self.log_delivery_attempt(stack_id, success=True, operation='push')
        
        return stack_id
    
    def pop_reply(self) -> Optional[Dict]:
        """Pop the most recent pending reply from stack"""
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT id, timestamp, context_json, reply_content, percentage_complete, metadata_json, content_hash
        FROM reply_stack 
        WHERE status = 'pending' 
        ORDER BY id DESC 
        LIMIT 1
        ''')
        
        row = cursor.fetchone()
        if not row:
            return None
        
        reply_id, timestamp, context_json, content, percentage, metadata_json, content_hash = row
        
        # Mark as delivering
        cursor.execute('UPDATE reply_stack SET status = "delivering" WHERE id = ?', (reply_id,))
        self.conn.commit()
        
        return {
            'id': reply_id,
            'timestamp': timestamp,
            'context': json.loads(context_json),
            'content': content,
            'percentage_complete': percentage,
            'metadata': json.loads(metadata_json) if metadata_json else {},
            'content_hash': content_hash
        }
    
    def mark_delivered(self, reply_id: int, truncation_detected: bool = False):
        """Mark a reply as successfully delivered"""
        cursor = self.conn.cursor()
        cursor.execute('''
        UPDATE reply_stack 
        SET status = 'delivered', 
            delivered_at = ?,
            truncated_detected = ?,
            replay_count = replay_count + 1
        WHERE id = ?
        ''', (datetime.now(timezone.utc).isoformat(), truncation_detected, reply_id))
        self.conn.commit()
    
    def mark_failed(self, reply_id: int, error_message: str = "Delivery failed"):
        """Mark a reply as failed delivery"""
        cursor = self.conn.cursor()
        cursor.execute('''
        UPDATE reply_stack 
        SET status = 'failed'
        WHERE id = ?
        ''', (reply_id,))
        self.conn.commit()
        
        self.log_delivery_attempt(reply_id, success=False, error_message=error_message)
    
    def log_delivery_attempt(self, 
                            stack_id: int,
                            success: bool = True,
                            truncation_detected: bool = False,
                            bytes_sent: Optional[int] = None,
                            bytes_received: Optional[int] = None,
                            error_message: Optional[str] = None,
                            network_conditions: Optional[Dict] = None,
                            operation: str = 'delivery'):
        """Log a delivery attempt"""
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT INTO delivery_log 
        (stack_id, attempt_timestamp, success, truncation_detected, bytes_sent, bytes_received, error_message, network_conditions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            stack_id,
            datetime.now(timezone.utc).isoformat(),
            success,
            truncation_detected,
            bytes_sent,
            bytes_received,
            error_message,
            json.dumps(network_conditions) if network_conditions else None
        ))
        self.conn.commit()
    
    def get_pending_count(self) -> int:
        """Get count of pending replies"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM reply_stack WHERE status = "pending"')
        return cursor.fetchone()[0]
    
    def get_replay_candidates(self, max_age_hours: int = 24) -> List[Dict]:
        """Get replies that might need replay due to truncation"""
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT id, timestamp, context_json, reply_content, percentage_complete
        FROM reply_stack 
        WHERE (truncated_detected = TRUE OR status = 'failed')
          AND datetime(timestamp) > datetime('now', ?)
        ORDER BY timestamp DESC
        ''', (f'-{max_age_hours} hours',))
        
        candidates = []
        for row in cursor.fetchall():
            reply_id, timestamp, context_json, content, percentage = row
            candidates.append({
                'id': reply_id,
                'timestamp': timestamp,
                'context': json.loads(context_json),
                'content': content,
                'percentage_complete': percentage
            })
        
        return candidates
    
    def get_stack_summary(self) -> Dict:
        """Get summary of stack state"""
        cursor = self.conn.cursor()
        
        cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN truncated_detected = TRUE THEN 1 ELSE 0 END) as truncated,
            MAX(timestamp) as latest,
            MIN(timestamp) as earliest
        FROM reply_stack
        ''')
        
        row = cursor.fetchone()
        return {
            'total': row[0],
            'pending': row[1],
            'delivered': row[2],
            'failed': row[3],
            'truncated': row[4],
            'latest': row[5],
            'earliest': row[6]
        }
    
    def cleanup_old_entries(self, days_to_keep: int = 7):
        """Clean up old stack entries"""
        cursor = self.conn.cursor()
        cursor.execute('''
        DELETE FROM reply_stack 
        WHERE datetime(timestamp) < datetime('now', ?)
          AND status = 'delivered'
          AND truncated_detected = FALSE
        ''', (f'-{days_to_keep} days',))
        
        deleted = cursor.rowcount
        self.conn.commit()
        return deleted
    
    def verify_integrity(self) -> Dict:
        """Verify stack integrity (hashes match)"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, reply_content, content_hash FROM reply_stack')
        
        mismatches = []
        for reply_id, content, stored_hash in cursor.fetchall():
            current_hash = hashlib.sha256(content.encode()).hexdigest()
            if current_hash != stored_hash:
                mismatches.append({
                    'id': reply_id,
                    'stored_hash': stored_hash,
                    'current_hash': current_hash
                })
        
        return {
            'total_checked': cursor.rowcount,
            'mismatches': mismatches,
            'integrity_ok': len(mismatches) == 0
        }
    
    def close(self):
        """Close database connection"""
        self.conn.close()

# Subway-specific detection and handling
class SubwayLagHandler:
    """Handle subway-specific lag and truncation detection"""
    
    def __init__(self, stack: ReplyStack):
        self.stack = stack
        self.lag_threshold_ms = 5000  # 5 seconds
        self.truncation_patterns = [
            '...', '[[truncated]]', '[incomplete]', '(cut off)'
        ]
    
    def detect_truncation(self, reply_content: str, expected_length: int) -> bool:
        """Detect if reply was truncated"""
        # Check for truncation patterns
        for pattern in self.truncation_patterns:
            if pattern in reply_content:
                return True
        
        # Check if significantly shorter than expected
        if expected_length > 0 and len(reply_content) < expected_length * 0.7:
            return True
        
        # Check for incomplete sentences at end
        lines = reply_content.strip().split('\n')
        if lines:
            last_line = lines[-1].strip()
            if last_line and last_line[-1] not in ['.', '!', '?', ']', ')', '}']:
                if not last_line.endswith('...'):  # Intentional ellipsis
                    return True
        
        return False
    
    def record_lag_event(self, rtt_ms: int, packet_loss: float):
        """Record a subway lag event"""
        return self.stack.record_subway_condition(
            condition=f'lag_{rtt_ms}ms',
            lag_detected=True,
            rtt_ms=rtt_ms,
            packet_loss=packet_loss,
            location={'transport': 'subway', 'environment': 'underground'}
        )
    
    def handle_possible_truncation(self, 
                                  reply_id: int, 
                                  sent_content: str, 
                                  received_feedback: Optional[str] = None):
        """Handle possible truncation of a reply"""
        truncation_detected = False
        
        if received_feedback:
            # Check if feedback indicates truncation
            if any(indicator in received_feedback.lower() 
                   for indicator in ['truncated', 'incomplete', 'cut off', '...']):
                truncation_detected = True
        
        # Also check the sent content itself
        if self.detect_truncation(sent_content, len(sent_content)):
            truncation_detected = True
        
        if truncation_detected:
            self.stack.mark_delivered(reply_id, truncation_detected=True)
            # Log the truncation
            self.stack.log_delivery_attempt(
                reply_id,
                success=True,  # technically delivered, but truncated
                truncation_detected=True,
                bytes_sent=len(sent_content),
                network_conditions={'subway_lag': True, 'truncation': True}
            )
            return True
        
        return False
    
    def get_reconnect_protocol(self) -> Dict:
        """Get protocol for reconnection after subway outage"""
        return {
            'action': 'replay_pending',
            'check_stack': True,
            'replay_truncated': True,
            'max_replays': 3,
            'delay_between_ms': 2000,
            'verification_required': True
        }

# Usage example
if __name__ == "__main__":
    stack = ReplyStack()
    handler = SubwayLagHandler(stack)
    
    # Record current subway condition
    handler.record_lag_event(rtt_ms=12000, packet_loss=0.3)
    
    # Example reply push
    context = {
        'subway_lag': True,
        'connectivity': 'intermittent',
        'failover_active': True
    }
    
    reply_id = stack.push_reply(
        reply_content="[[reply_to_current]] Test reply during subway lag.",
        context=context,
        percentage_complete=5,
        metadata={'subway_line': 'U8', 'station': 'Hermannplatz'}
    )
    
    print(f"Pushed reply {reply_id}")
    print(f"Pending count: {stack.get_pending_count()}")
    print(f"Stack summary: {stack.get_stack_summary()}")
    
    stack.close()