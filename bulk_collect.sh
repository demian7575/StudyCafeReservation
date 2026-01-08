#!/bin/bash

echo "Starting bulk data collection for DynamoDB..."

# 과거 90일간의 데이터를 수집
for i in {0..89}; do
    # 날짜 계산 (Linux/macOS 호환)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        date_str=$(date -v-${i}d +%Y-%m-%d)
    else
        # Linux
        date_str=$(date -d "${i} days ago" +%Y-%m-%d)
    fi
    
    echo "Processing date: $date_str (day $((i+1))/90)"
    
    # Lambda 함수 호출하여 해당 날짜 데이터 수집
    payload="{\"httpMethod\": \"GET\", \"queryStringParameters\": {\"date\": \"$date_str\"}}"
    encoded_payload=$(echo "$payload" | base64 | tr -d '\n')
    
    aws lambda invoke \
        --function-name refresh-service \
        --payload "$encoded_payload" \
        --region ap-northeast-2 \
        /tmp/response_${date_str}.json > /dev/null 2>&1
    
    # API 호출 제한을 위한 대기
    sleep 1
    
    # 진행상황 출력
    if [ $((($i + 1) % 10)) -eq 0 ]; then
        echo "Progress: $((i+1))/90 days processed"
    fi
done

echo "Bulk data collection completed!"
echo "All historical data has been processed and cached in DynamoDB."
