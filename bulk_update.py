import json
import urllib3
import boto3
import os
import time
from datetime import datetime, timedelta

# AWS 리소스 초기화
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
http = urllib3.PoolManager()

def get_new_token():
    """새 토큰 발급"""
    comepass_id = "01067898449"
    comepass_pwd = "0000"
    
    login_url = 'https://api.comepass.kr/login/admin'
    login_headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://place.comepass.kr',
        'Referer': 'https://place.comepass.kr/',
        'X-Dmon-Request-From': 'place_admin_web',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    login_data = {"id": comepass_id, "pwd": comepass_pwd}
    login_response = http.request('POST', login_url, body=json.dumps(login_data), headers=login_headers)
    result = json.loads(login_response.data.decode('utf-8'))
    return result

def get_reservations_for_date(date_str, access_token, p_code):
    """특정 날짜의 예약 데이터 가져오기"""
    try:
        studyroom_url = f'https://api.comepass.kr/place/studyroom?date={date_str}'
        studyroom_headers = {
            'Accept': 'application/json, text/plain, */*',
            'Authorization': f'Bearer {access_token}',
            'Origin': 'https://place.comepass.kr',
            'Referer': 'https://place.comepass.kr/',
            'X-Dmon-Place-Code': p_code,
            'X-Dmon-Request-From': 'place_admin_web',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        studyroom_response = http.request('GET', studyroom_url, headers=studyroom_headers)
        studyroom_data = json.loads(studyroom_response.data.decode('utf-8'))
        
        if studyroom_data.get('result') == 'success':
            return studyroom_data.get('list', [])
        else:
            print(f"API error for {date_str}: {studyroom_data}")
            return []
            
    except Exception as e:
        print(f"Error getting data for {date_str}: {e}")
        return []

def save_to_dynamodb(date_str, raw_data):
    """DynamoDB에 데이터 저장"""
    try:
        table = dynamodb.Table('studyroom-data-cache')
        
        table.put_item(Item={
            'date': date_str,
            'raw_data': raw_data,
            'cached_at': int(datetime.now().timestamp()),
            'last_updated': int(datetime.now().timestamp())
        })
        print(f"Saved {len(raw_data)} records for {date_str}")
        return True
    except Exception as e:
        print(f"Error saving data for {date_str}: {e}")
        return False

def bulk_update_dynamodb():
    """과거 데이터 일괄 업데이트"""
    print("Starting bulk update of DynamoDB...")
    
    # 토큰 발급
    try:
        token_data = get_new_token()
        access_token = token_data['access_token']
        p_code = token_data['p_code']
        print(f"Token obtained successfully")
    except Exception as e:
        print(f"Failed to get token: {e}")
        return
    
    # 현재부터 과거 180일까지 데이터 수집
    end_date = datetime.now()
    total_days = 180
    success_count = 0
    error_count = 0
    
    for i in range(total_days):
        current_date = end_date - timedelta(days=i)
        date_str = current_date.strftime('%Y-%m-%d')
        
        print(f"Processing {date_str} ({i+1}/{total_days})")
        
        # 데이터 가져오기
        reservations = get_reservations_for_date(date_str, access_token, p_code)
        
        if reservations:
            # DynamoDB에 저장
            if save_to_dynamodb(date_str, reservations):
                success_count += 1
            else:
                error_count += 1
        else:
            print(f"No data for {date_str}")
        
        # API 호출 제한 방지
        time.sleep(0.5)
        
        # 진행상황 출력
        if (i + 1) % 10 == 0:
            print(f"Progress: {i+1}/{total_days} days processed, {success_count} successful, {error_count} errors")
    
    print(f"\nBulk update completed!")
    print(f"Total days processed: {total_days}")
    print(f"Successful: {success_count}")
    print(f"Errors: {error_count}")

if __name__ == "__main__":
    bulk_update_dynamodb()
