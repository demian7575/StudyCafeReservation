import json
import urllib3
import boto3
import os
import time
from datetime import datetime

# 전역 변수로 재사용 가능한 리소스 초기화
dynamodb = boto3.resource('dynamodb')
http = urllib3.PoolManager()

def lambda_handler(event, context):
    start_time = time.time()
    print(f"Lambda started at {datetime.now()}")
    
    # favicon.ico 요청 처리
    if event.get('path') == '/favicon.ico':
        return {
            'statusCode': 204,
            'headers': {'Content-Type': 'image/x-icon'},
            'body': ''
        }
    
    # GET 요청이고 Accept 헤더가 text/html이면 HTML 페이지 반환
    if event.get('httpMethod') == 'GET' and 'text/html' in event.get('headers', {}).get('Accept', ''):
        result = serve_html()
        print(f"HTML served in {time.time() - start_time:.2f}s")
        return result
    
    # 그 외에는 API 응답
    query_params = event.get('queryStringParameters') or {}
    selected_date = query_params.get('date', datetime.now().strftime('%Y-%m-%d'))
    result = get_reservations(selected_date)
    print(f"API response completed in {time.time() - start_time:.2f}s")
    return result

def get_cached_token():
    """DynamoDB에서 캐시된 토큰 가져오기"""
    start_time = time.time()
    try:
        table = dynamodb.Table('aipm-backend-prod-stories')
        
        response = table.get_item(Key={'id': 1})  # 숫자 키 사용
        print(f"DynamoDB query took {time.time() - start_time:.2f}s")
        
        if 'Item' in response:
            token_data = response['Item']
            expires_at = int(token_data.get('expires_at', 0))
            current_time = int(datetime.now().timestamp())
            
            print(f"Token expires at: {datetime.fromtimestamp(expires_at)}")
            print(f"Current time: {datetime.fromtimestamp(current_time)}")
            print(f"Time until expiry: {expires_at - current_time} seconds")
            
            # 토큰이 아직 유효한지 확인 (5분 여유)
            if expires_at > current_time + 300:
                print("Using cached token (valid)")
                return {
                    'access_token': token_data['access_token'],
                    'p_code': token_data['p_code'],
                    'p_name': token_data['p_name'],
                    'expires_at': expires_at
                }
            else:
                print(f"Cached token expired or expiring soon (expires in {expires_at - current_time}s)")
        else:
            print("No cached token found")
    except Exception as e:
        print(f"Error getting cached token: {e}")
    return None

def save_token(token_data):
    """DynamoDB에 토큰 저장"""
    start_time = time.time()
    try:
        table = dynamodb.Table('aipm-backend-prod-stories')
        
        expires_at = int(token_data['access_token_expires_in'])
        current_time = int(datetime.now().timestamp())
        
        print(f"Saving token that expires at: {datetime.fromtimestamp(expires_at)}")
        print(f"Token valid for: {expires_at - current_time} seconds")
        
        table.put_item(Item={
            'id': 1,  # 숫자 키 사용
            'access_token': token_data['access_token'],
            'p_code': token_data['p_code'],
            'p_name': token_data['p_name'],
            'expires_at': expires_at,
            'updated_at': current_time
        })
        print(f"Token saved in {time.time() - start_time:.2f}s")
    except Exception as e:
        print(f"Error saving token: {e}")

def get_new_token():
    """새 토큰 발급"""
    start_time = time.time()
    print("Getting new token from Comepass API")
    
    # 환경변수에서 자격증명 가져오기
    comepass_id = os.environ.get('COMEPASS_ID')
    comepass_pwd = os.environ.get('COMEPASS_PWD')
    
    if not comepass_id or not comepass_pwd:
        raise Exception('COMEPASS_ID 또는 COMEPASS_PWD 환경변수가 설정되지 않았습니다')
    
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
    print(f"New token obtained in {time.time() - start_time:.2f}s")
    return result

def serve_html():
    html_content = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>스터디카페 예약 현황</title>
    <link rel="icon" href="data:,">
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; height: 100dvh; display: flex; flex-direction: column; overflow-x: hidden; }
        .header { background: #f5f5f5; padding: 10px; border-bottom: 2px solid #ddd; flex-shrink: 0; text-align: center; }
        .header h1 { margin: 0; }
        .content { flex: 0 0 auto; overflow-y: visible; padding: 0; }
        .spacer { flex: 1; }
        .footer { background: #f5f5f5; padding: 10px; border-top: 2px solid #ddd; flex-shrink: 0; }
        .controls { margin: 0; }
        input[type="date"] { padding: 8px; margin-right: 10px; border: 1px solid #ddd; border-radius: 4px; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
        button:hover { background: #0056b3; }
        .schedule-table { width: 100%; border-collapse: collapse; margin: 0; display: block; }
        .schedule-table thead { display: table; width: 100%; table-layout: fixed; }
        .schedule-table tbody { display: block; max-height: calc(100dvh - 180px); overflow-y: auto; overflow-x: hidden; }
        .schedule-table tbody tr { display: table; width: 100%; table-layout: fixed; height: calc((100dvh - 180px) / 14); }
        .schedule-table tfoot { display: table; width: 100%; table-layout: fixed; }
        .schedule-table th, .schedule-table td { border: 1px solid #ddd; padding: 2px 8px; text-align: center; }
        .schedule-table th { background-color: #f2f2f2; font-weight: bold; }
        .time-header { background-color: #e9ecef; font-weight: bold; }
        .reserved { background-color: #d4edda; }
        .used { background-color: #f8d7da; }
        .total-row { background-color: #fff3cd; font-weight: bold; }
    </style>
</head>
<body>
    <div class="header">
        <h1>스터디카페 예약 현황</h1>
    </div>
    <div class="content">
        <div id="reservationDisplay"></div>
    </div>
    <div class="spacer"></div>
    <div class="footer">
        <div class="controls">
            <input type="date" id="dateSelector" value="" onchange="loadReservations()">
            <button onclick="loadYesterday()">전일</button>
            <button onclick="loadTomorrow()">익일</button>
        </div>
    </div>

    <script>
        // Safari 호환성을 위한 날짜 설정
        function setDateValue(date) {
            const dateInput = document.getElementById('dateSelector');
            // Safari에서 더 안정적인 날짜 포맷팅
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const dateString = year + '-' + month + '-' + day;
            
            dateInput.value = dateString;
            
            // Safari에서 값이 제대로 설정되었는지 확인
            if (dateInput.value !== dateString) {
                setTimeout(() => {
                    dateInput.value = dateString;
                }, 50); // 시간을 늘려서 더 안정적으로
            }
        }
        
        // 현재 날짜로 초기화 (서울 시간 기준)
        function getTodayInSeoul() {
            const now = new Date();
            // Safari에서 더 안정적인 시간대 처리
            const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
            const seoulTime = new Date(utc + (9 * 60 * 60 * 1000));
            return seoulTime;
        }
        
        setDateValue(getTodayInSeoul());
        
        function loadYesterday() {
            const dateInput = document.getElementById('dateSelector');
            const currentDateStr = dateInput.value;
            if (currentDateStr) {
                // Safari에서 더 안정적인 날짜 파싱
                const parts = currentDateStr.split('-');
                const currentDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                currentDate.setDate(currentDate.getDate() - 1);
                setDateValue(currentDate);
                loadReservations();
            }
        }
        
        function loadTomorrow() {
            const dateInput = document.getElementById('dateSelector');
            const currentDateStr = dateInput.value;
            if (currentDateStr) {
                // Safari에서 더 안정적인 날짜 파싱
                const parts = currentDateStr.split('-');
                const currentDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                currentDate.setDate(currentDate.getDate() + 1);
                setDateValue(currentDate);
                loadReservations();
            }
        }

        async function loadReservations() {
            const reservationDiv = document.getElementById('reservationDisplay');
            const selectedDate = document.getElementById('dateSelector').value;
            
            try {
                // Safari 호환성을 위해 URL 구성 방식 변경
                const baseUrl = window.location.origin + window.location.pathname;
                const url = baseUrl + '?date=' + encodeURIComponent(selectedDate) + '&_t=' + Date.now();
                
                const response = await fetch(url, {
                    method: 'GET',
                    headers: { 
                        'Accept': 'application/json',
                        'Cache-Control': 'no-cache'
                    }
                });
                
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                
                const data = await response.json();
                
                if (response.ok && !data.error) {
                    displaySchedule(data);
                } else {
                    throw new Error(data.error || '예약 현황 조회 실패');
                }
            } catch (error) {
                console.error('Error loading reservations:', error);
            }
        }

        function displaySchedule(data) {
            const reservationDiv = document.getElementById('reservationDisplay');
            
            // 룸 이름 매핑
            const roomNames = {
                '1번 스터디룸': '2인 오피스룸',
                '2번 스터디룸': '4인 스터디룸', 
                '3번 스터디룸': '2인 스터디룸'
            };
            
            // 시간대별 예약 데이터 구성
            const timeSlots = [];
            const roomData = {};
            const roomTotals = {};
            
            // 0시부터 23시까지 시간대 생성
            for (let hour = 0; hour < 24; hour++) {
                const timeStr = (hour < 10 ? '0' + hour : hour) + ':00';
                timeSlots.push(timeStr);
            }
            
            // 룸별 데이터 초기화
            Object.values(roomNames).forEach(roomName => {
                roomData[roomName] = {};
                roomTotals[roomName] = 0;
                timeSlots.forEach(time => {
                    roomData[roomName][time] = '';
                });
            });
            
            // 예약 데이터 처리
            if (data.reservations && data.reservations.list) {
                if (data.reservations.list.length > 0) {
                    console.log('First reservation data:', JSON.stringify(data.reservations.list[0], null, 2));
                }
                data.reservations.list.forEach(reservation => {
                    // 취소 상태 디버깅
                    console.log('Reservation status check:', {
                        name: reservation.m_nm,
                        s_status: reservation.s_status,
                        cancel_yn: reservation.cancel_yn,
                        status: reservation.status,
                        cancelled: reservation.cancelled,
                        is_cancelled: reservation.is_cancelled
                    });
                    
                    // 취소된 예약 제외 (다양한 취소 상태 필드 확인)
                    if (reservation.s_status === 'C' || reservation.s_status === 'CANCEL' || 
                        reservation.cancel_yn === 'Y' || reservation.cancel_yn === 'YES' ||
                        reservation.status === 'cancelled' || reservation.cancelled === true ||
                        reservation.is_cancelled === true || reservation.is_cancelled === 'Y' ||
                        reservation.s_state === 'REFUND' || reservation.ord_refund_step === 'SUCCESS') {
                        console.log('Cancelled reservation skipped:', reservation.m_nm);
                        return;
                    }
                    
                    const roomName = roomNames[reservation.sg_name] || reservation.sg_name;
                    const startHour = parseInt(reservation.s_s_time.split(':')[0]);
                    const endHour = parseInt(reservation.s_e_time.split(':')[0]);
                    const endMin = parseInt(reservation.s_e_time.split(':')[1]);
                    
                    // 사용시간(분)을 시간으로 변환하고 올림
                    const useTimeMinutes = parseInt(reservation.s_use_time);
                    const useTimeHours = Math.ceil(useTimeMinutes / 60);
                    
                    roomTotals[roomName] += useTimeHours;
                    
                    // 시간 표시 로직 (전일부터 시작된 예약 고려)
                    if (endHour < startHour) {
                        // 자정을 넘어가는 예약: 0시부터 끝시간까지만 표시 (당일 부분)
                        for (let hour = 0; hour < endHour; hour++) {
                            const timeKey = (hour < 10 ? '0' + hour : hour) + ':00';
                            if (roomData[roomName] && roomData[roomName][timeKey] !== undefined) {
                                roomData[roomName][timeKey] = reservation.m_nm;
                            }
                        }
                        // 끝 시간에 분이 있는 경우
                        if (endMin > 0) {
                            const endTimeKey = (endHour < 10 ? '0' + endHour : endHour) + ':00';
                            if (roomData[roomName] && roomData[roomName][endTimeKey] !== undefined) {
                                roomData[roomName][endTimeKey] = reservation.m_nm;
                            }
                        }
                    } else {
                        // 일반적인 경우: 시작 시간부터 끝 시간 전까지
                        for (let hour = startHour; hour < endHour; hour++) {
                            const timeKey = (hour < 10 ? '0' + hour : hour) + ':00';
                            if (roomData[roomName] && roomData[roomName][timeKey] !== undefined) {
                                roomData[roomName][timeKey] = reservation.m_nm;
                            }
                        }
                        // 끝 시간에 분이 있는 경우
                        if (endMin > 0) {
                            const endTimeKey = (endHour < 10 ? '0' + endHour : endHour) + ':00';
                            if (roomData[roomName] && roomData[roomName][endTimeKey] !== undefined) {
                                roomData[roomName][endTimeKey] = reservation.m_nm;
                            }
                        }
                    }
                    

                });
            }
            
            // 테이블 생성
            let html = '<table class="schedule-table"><thead><tr><th class="time-header">시간</th>';
            
            Object.values(roomNames).forEach(roomName => {
                html += `<th>${roomName}</th>`;
            });
            html += '</tr></thead><tbody>';
            
            // 시간대별 행 생성
            timeSlots.forEach(time => {
                html += `<tr><td class="time-header">${time}</td>`;
                Object.values(roomNames).forEach(roomName => {
                    const cellData = roomData[roomName][time];
                    const cellClass = cellData ? 'used' : '';
                    html += `<td class="${cellClass}">${cellData}</td>`;
                });
                html += '</tr>';
            });
            
            html += '</tbody><tfoot>';
            
            // 총 시간 행
            html += '<tr class="total-row"><td>총 시간</td>';
            Object.values(roomNames).forEach(roomName => {
                html += `<td>${roomTotals[roomName]}시간</td>`;
            });
            html += '</tr>';
            
            html += '</tfoot></table>';
            
            reservationDiv.innerHTML = html;
            
            // Scroll to 09:00 row
            setTimeout(() => {
                const tbody = document.querySelector('.schedule-table tbody');
                if (tbody) {
                    const rowHeight = tbody.querySelector('tr')?.offsetHeight || 30;
                    tbody.scrollTop = 9 * rowHeight;
                }
            }, 100);
        }
        
        window.onload = function() {
            loadReservations();
        };
    </script>
</body>
</html>'''
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': html_content
    }

def get_reservations(date):
    start_time = time.time()
    
    try:
        # 캐시된 토큰 확인
        cached_token = get_cached_token()
        
        if cached_token:
            # 캐시된 토큰 사용
            access_token = cached_token['access_token']
            p_code = cached_token['p_code']
            p_name = cached_token['p_name']
            token_expires = cached_token['expires_at']
        else:
            # 새 토큰 발급
            login_result = get_new_token()
            access_token = login_result['access_token']
            p_code = login_result['p_code']
            p_name = login_result['p_name']
            token_expires = login_result['access_token_expires_in']
            
            # 토큰 저장
            save_token(login_result)
        
        # 예약 현황 조회
        api_start = time.time()
        studyroom_url = f'https://api.comepass.kr/place/studyroom?date={date}'
        
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
        print(f"Studyroom API call took {time.time() - api_start:.2f}s")
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'place_name': p_name,
                'date': date,
                'reservations': studyroom_data,
                'token_expires': token_expires,
                'token_cached': cached_token is not None,
                'processing_time': f"{time.time() - start_time:.2f}s"
            })
        }
        
    except Exception as e:
        print(f"Error in get_reservations: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e), 'processing_time': f"{time.time() - start_time:.2f}s"})
        }
