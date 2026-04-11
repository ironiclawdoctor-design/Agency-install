#!/bin/bash
# Financial Weaknesses Monitor
# Monitors top 2 external financial weaknesses:
# 1. Traditional Financial API Blocking
# 2. Selective Service Restrictions

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_DIR="/root/.openclaw/workspace/monitoring"
REPORT_FILE="$LOG_DIR/financial-weaknesses-$(date +%Y%m%d-%H%M).json"
mkdir -p "$LOG_DIR"

# Initialize JSON report
cat > "$REPORT_FILE" << EOF
{
  "monitoring_id": "FWM-$(date +%Y%m%d%H%M%S)",
  "timestamp": "$TIMESTAMP",
  "weaknesses_monitored": [
    "traditional_financial_api_blocking",
    "selective_service_restrictions"
  ]
}
EOF

# Function to test API with timeout
test_api() {
    local name=$1
    local url=$2
    local pattern=$3
    
    echo "Testing $name..."
    local start_time=$(date +%s%N)
    
    # Use curl with timeout
    local response=$(timeout 10 curl -s "$url" 2>/dev/null || echo "TIMEOUT_OR_ERROR")
    local end_time=$(date +%s%N)
    local duration_ms=$(( (end_time - start_time) / 1000000 ))
    
    if [ "$response" = "TIMEOUT_OR_ERROR" ]; then
        echo "{\"api\": \"$name\", \"status\": \"blocked\", \"duration_ms\": $duration_ms, \"error\": \"timeout_or_connection_refused\"}"
        return 1
    elif echo "$response" | grep -q "$pattern"; then
        echo "{\"api\": \"$name\", \"status\": \"working\", \"duration_ms\": $duration_ms, \"pattern_matched\": true}"
        return 0
    else
        echo "{\"api\": \"$name\", \"status\": \"unexpected_response\", \"duration_ms\": $duration_ms, \"response_preview\": \"$(echo "$response" | head -c 100)\"}"
        return 2
    fi
}

# Function to test basic connectivity
test_connectivity() {
    echo "Testing basic internet connectivity..."
    
    # Test ping to Google DNS
    if ping -c 2 -W 2 8.8.8.8 > /dev/null 2>&1; then
        echo "{\"test\": \"ping_8.8.8.8\", \"status\": \"working\", \"details\": \"basic_internet_connectivity_ok\"}"
        return 0
    else
        echo "{\"test\": \"ping_8.8.8.8\", \"status\": \"blocked\", \"details\": \"basic_internet_connectivity_failed\"}"
        return 1
    fi
}

# Function to test selective restrictions
test_selective_restrictions() {
    echo "Testing selective service restrictions..."
    
    # Test working API (CoinGecko)
    local crypto_test=$(test_api "coingecko" "https://api.coingecko.com/api/v3/ping" "gecko_says")
    
    # Test blocked API (Yahoo Finance)
    local finance_test=$(test_api "yahoo_finance" "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC" "regularMarketPrice")
    
    # Analyze pattern
    if echo "$crypto_test" | grep -q "\"status\": \"working\"" && \
       echo "$finance_test" | grep -q "\"status\": \"blocked\""; then
        echo "{\"pattern\": \"selective_restrictions\", \"detected\": true, \"details\": \"crypto_working_finance_blocked\"}"
        return 0
    else
        echo "{\"pattern\": \"selective_restrictions\", \"detected\": false, \"details\": \"pattern_not_clear\"}"
        return 1
    fi
}

# Function to test traditional financial APIs
test_traditional_apis() {
    echo "Testing traditional financial APIs..."
    
    local blocked_count=0
    local total_tests=0
    
    # Test traditional financial APIs
    local apis=(
        "yahoo_finance:https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC:regularMarketPrice"
        "coincap:https://api.coincap.io/v2/assets/bitcoin:priceUsd"
        "nasdaq:https://www.nasdaq.com:DOCTYPE"
    )
    
    for api in "${apis[@]}"; do
        IFS=':' read -r name url pattern <<< "$api"
        total_tests=$((total_tests + 1))
        
        local result=$(test_api "$name" "$url" "$pattern")
        if echo "$result" | grep -q "\"status\": \"blocked\""; then
            blocked_count=$((blocked_count + 1))
        fi
    done
    
    local blocking_ratio=$(echo "scale=2; $blocked_count / $total_tests" | bc)
    
    if (( $(echo "$blocking_ratio >= 0.66" | bc -l) )); then
        echo "{\"weakness\": \"traditional_financial_api_blocking\", \"detected\": true, \"blocking_ratio\": $blocking_ratio, \"blocked\": $blocked_count, \"total\": $total_tests}"
        return 0
    else
        echo "{\"weakness\": \"traditional_financial_api_blocking\", \"detected\": false, \"blocking_ratio\": $blocking_ratio, \"blocked\": $blocked_count, \"total\": $total_tests}"
        return 1
    fi
}

# Main monitoring execution
echo "Starting financial weaknesses monitoring at $TIMESTAMP"

# Create results array
results=()

# Test 1: Basic Connectivity
result1=$(test_connectivity)
results+=("$result1")

# Test 2: Traditional Financial API Blocking
result2=$(test_traditional_apis)
results+=("$result2")

# Test 3: Selective Service Restrictions
result3=$(test_selective_restrictions)
results+=("$result3")

# Generate final report
echo "Generating monitoring report..."

# Update JSON report with results
{
    echo '"results": ['
    printf '    %s' "${results[0]}"
    for ((i=1; i<${#results[@]}; i++)); do
        printf ',\n    %s' "${results[$i]}"
    done
    echo ''
    echo '  ]'
} >> "$REPORT_FILE"

echo '}' >> "$REPORT_FILE"

# Check for anomalies
if echo "$result2" | grep -q "\"detected\": true" || \
   echo "$result3" | grep -q "\"detected\": true"; then
    echo "ANOMALY_DETECTED: Financial weaknesses confirmed"
    echo "Report saved to: $REPORT_FILE"
    exit 1
else
    echo "STATUS_NOMINAL: No financial weaknesses detected"
    echo "Report saved to: $REPORT_FILE"
    exit 0
fi