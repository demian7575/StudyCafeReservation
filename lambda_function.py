import json
import urllib3
import boto3
import os
import time
from datetime import datetime, timedelta

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
    
    # 데이터 수집 엔드포인트들
    if event.get('path') == '/collect-data':
        return collect_and_store_reservation_data()
    
    if event.get('path') == '/collect-past':
        return collect_past_data()
    
    if event.get('path') == '/collect-three-months':
        return collect_three_months_data()
    
    if event.get('path') == '/auto-collect':
        return auto_sync_data()
    
    # API 엔드포인트들
    if event.get('path') == '/api/trends':
        query_params = event.get('queryStringParameters') or {}
        start_date = query_params.get('start', '')
        end_date = query_params.get('end', '')
        analysis_type = query_params.get('type', 'weekly')
        return get_trends_data(start_date, end_date, analysis_type)
    
    # 페이지 엔드포인트들
    if event.get('path') == '/trends':
        return serve_trends_page()
    
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

def serve_trends_page():
    """추이분석 페이지"""
    html = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>스터디카페 추이분석</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f8f9fa; position: relative; }
        .home-link { position: absolute; top: 20px; right: 20px; background: #007bff; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; }
        .home-link:hover { background: #0056b3; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .nav { margin: 20px 0; text-align: center; }
        .nav-btn { background: #6c757d; color: white; padding: 10px 20px; border: none; border-radius: 4px; margin: 0 10px; cursor: pointer; text-decoration: none; display: inline-block; }
        .nav-btn.active { background: #007bff; }
        .nav-btn:hover { opacity: 0.8; }
        .controls { margin: 20px 0; text-align: center; }
        .period-controls { margin: 20px 0; text-align: center; }
        input[type="date"] { padding: 8px; margin: 0 10px; border: 1px solid #ddd; border-radius: 4px; }
        button { background: #007bff; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin: 0 5px; }
        button:hover { background: #0056b3; }
        button.active { background: #28a745; }
        .chart-container { background: white; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center; }
        .loading { text-align: center; color: #666; padding: 50px; }
        .chart-canvas { width: 100%; max-height: 400px; }
        .chart-grid { display: grid; grid-template-columns: 1fr; gap: 20px; }
    </style>
</head>
<body>
    <a href="/prod/" class="home-link">스터디카페 관리</a>
    <div class="container">
        <div class="header">
            <h1>📈 스터디카페 추이분석</h1>
        </div>
        
        <div class="controls">
            <button id="weeklyBtn" onclick="setTrendsType('weekly')" class="active">주별</button>
            <button id="monthlyBtn" onclick="setTrendsType('monthly')">월별</button>
        </div>
        
        <div class="period-controls">
            <input type="date" id="startDate" onchange="loadTrends()">
            <span>~</span>
            <input type="date" id="endDate" onchange="loadTrends()">
            <button onclick="setDefaultPeriod()">최근 2개월</button>
        </div>
        
        <div class="chart-grid">
            <div class="chart-container">
                <h3>매출 추이</h3>
                <canvas id="revenueChart" class="chart-canvas"></canvas>
                <div id="revenue-loading" class="loading" style="display:none">
                    <p>매출 데이터를 불러오는 중...</p>
                </div>
            </div>
            
            <div class="chart-container">
                <h3>예약 건수 추이</h3>
                <canvas id="reservationsChart" class="chart-canvas"></canvas>
                <div id="reservations-loading" class="loading" style="display:none">
                    <p>예약 데이터를 불러오는 중...</p>
                </div>
            </div>
            
            <div class="chart-container">
                <h3>사용 시간 추이</h3>
                <canvas id="hoursChart" class="chart-canvas"></canvas>
                <div id="hours-loading" class="loading" style="display:none">
                    <p>시간 데이터를 불러오는 중...</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let revenueChart = null;
        let reservationsChart = null;
        let hoursChart = null;
        let currentType = 'weekly';
        
        function setTrendsType(type) {
            currentType = type;
            document.getElementById('weeklyBtn').classList.toggle('active', type === 'weekly');
            document.getElementById('monthlyBtn').classList.toggle('active', type === 'monthly');
            loadTrends();
        }
        
        function setDefaultPeriod() {
            const today = new Date();
            const twoMonthsAgo = new Date(today);
            twoMonthsAgo.setMonth(twoMonthsAgo.getMonth() - 2);
            
            document.getElementById('startDate').value = twoMonthsAgo.toISOString().split('T')[0];
            document.getElementById('endDate').value = today.toISOString().split('T')[0];
            
            loadTrends();
        }
        
        function loadTrends() {
            const startDate = document.getElementById('startDate').value;
            const endDate = document.getElementById('endDate').value;
            
            if (!startDate || !endDate) {
                alert('시작일과 종료일을 모두 선택해주세요.');
                return;
            }
            
            if (new Date(startDate) > new Date(endDate)) {
                alert('시작일이 종료일보다 늦을 수 없습니다.');
                return;
            }
            
            // 미래 날짜 제한
            const today = new Date();
            if (new Date(endDate) > today) {
                alert('종료일은 오늘 날짜를 초과할 수 없습니다.');
                return;
            }
            
            // 로딩 표시
            document.getElementById('revenue-loading').style.display = 'block';
            document.getElementById('reservations-loading').style.display = 'block';
            document.getElementById('hours-loading').style.display = 'block';
            
            // 기존 차트 제거
            if (revenueChart) revenueChart.destroy();
            if (reservationsChart) reservationsChart.destroy();
            if (hoursChart) hoursChart.destroy();
            
            fetch(`/prod/api/trends?start=${startDate}&end=${endDate}&type=${currentType}`)
                .then(response => response.json())
                .then(data => displayTrends(data))
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('revenue-loading').innerHTML = '<p>데이터 로드 중 오류가 발생했습니다.</p>';
                    document.getElementById('reservations-loading').innerHTML = '<p>데이터 로드 중 오류가 발생했습니다.</p>';
                    document.getElementById('hours-loading').innerHTML = '<p>데이터 로드 중 오류가 발생했습니다.</p>';
                });
        }
        
        function displayTrends(data) {
            // 로딩 숨기기
            document.getElementById('revenue-loading').style.display = 'none';
            document.getElementById('reservations-loading').style.display = 'none';
            document.getElementById('hours-loading').style.display = 'none';
            
            const chartOptions = {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: 2,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            };
            
            // 매출 추이 차트
            const revenueCtx = document.getElementById('revenueChart').getContext('2d');
            revenueChart = new Chart(revenueCtx, {
                type: 'bar',
                data: {
                    labels: data.labels || [],
                    datasets: [{
                        label: '매출 (원)',
                        data: data.revenue || [],
                        backgroundColor: 'rgba(75, 192, 192, 0.8)',
                        borderColor: 'rgb(75, 192, 192)',
                        borderWidth: 1
                    }]
                },
                options: chartOptions
            });
            
            // 예약 건수 추이 차트
            const reservationsCtx = document.getElementById('reservationsChart').getContext('2d');
            reservationsChart = new Chart(reservationsCtx, {
                type: 'bar',
                data: {
                    labels: data.labels || [],
                    datasets: [{
                        label: '예약 건수',
                        data: data.reservations || [],
                        backgroundColor: 'rgba(255, 99, 132, 0.8)',
                        borderColor: 'rgb(255, 99, 132)',
                        borderWidth: 1
                    }]
                },
                options: chartOptions
            });
            
            // 사용 시간 추이 차트
            const hoursCtx = document.getElementById('hoursChart').getContext('2d');
            hoursChart = new Chart(hoursCtx, {
                type: 'bar',
                data: {
                    labels: data.labels || [],
                    datasets: [{
                        label: '사용 시간 (시간)',
                        data: data.hours || [],
                        backgroundColor: 'rgba(54, 162, 235, 0.8)',
                        borderColor: 'rgb(54, 162, 235)',
                        borderWidth: 1
                    }]
                },
                options: chartOptions
            });
        }
        
        window.onload = function() {
            setDefaultPeriod();
        };
    </script>
</body>
</html>'''
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': html
    }

def get_trends_data(start_date, end_date, analysis_type='weekly'):
    """추이분석 데이터 조회 (배치 쿼리)"""
    try:
        # 날짜 범위 생성
        dates = []
        current = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        while current <= end:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        # 배치 쿼리로 데이터 수집
        daily_data = {}
        
        # 25개씩 배치 처리
        for i in range(0, len(dates), 25):
            batch_dates = dates[i:i+25]
            
            # 배치 요청 구성
            request_items = {
                'studyroom-proxy-db': {
                    'Keys': [{'date': date} for date in batch_dates],
                    'ProjectionExpression': '#d, reservations',
                    'ExpressionAttributeNames': {'#d': 'date'}
                }
            }
            
            try:
                response = dynamodb.batch_get_item(RequestItems=request_items)
                
                # 응답 처리 (Python 객체 형식)
                if 'Responses' in response and 'studyroom-proxy-db' in response['Responses']:
                    print(f"Batch response items: {len(response['Responses']['studyroom-proxy-db'])}")
                    for item in response['Responses']['studyroom-proxy-db']:
                        date = item['date']  # Python 문자열
                        print(f"Processing date: {date}")
                        reservations = 0
                        hours = 0
                        revenue = 0
                        
                        if 'reservations' in item and item['reservations']:
                            print(f"Found {len(item['reservations'])} reservations for {date}")
                            for reservation in item['reservations']:
                                status = reservation.get('status', '')
                                user = reservation.get('user', '')
                                if status in ['USED', 'RESERVED'] and user not in ['최은숙', '배준기']:
                                    reservations += 1
                                    hours += float(reservation.get('hours', 0)) / 60
                                    revenue += int(reservation.get('revenue', 0))
                        
                        print(f"Final counts for {date}: {reservations} reservations, {hours} hours, {revenue} revenue")
                        daily_data[date] = {
                            'reservations': reservations,
                            'hours': hours,
                            'revenue': revenue
                        }
                else:
                    print(f"No batch response data found")
                
                # 누락된 날짜 처리
                for date in batch_dates:
                    if date not in daily_data:
                        daily_data[date] = {'reservations': 0, 'hours': 0, 'revenue': 0}
                        
            except Exception as e:
                print(f"Batch query error for dates {batch_dates}: {e}")
                # 배치 실패시 개별 쿼리로 폴백
                table = dynamodb.Table('studyroom-proxy-db')
                for date in batch_dates:
                    try:
                        response = table.get_item(Key={'date': date}, ProjectionExpression='reservations')
                        if 'Item' in response:
                            item = response['Item']
                            reservations = 0
                            hours = 0
                            revenue = 0
                            
                            if 'reservations' in item and item['reservations']:
                                for reservation in item['reservations']:
                                    status = reservation.get('status', '')
                                    user = reservation.get('user', '')
                                    if status in ['USED', 'RESERVED'] and user not in ['최은숙', '배준기']:
                                        reservations += 1
                                        hours += float(reservation.get('hours', 0)) / 60
                                        revenue += int(reservation.get('revenue', 0))
                            
                            daily_data[date] = {'reservations': reservations, 'hours': hours, 'revenue': revenue}
                        else:
                            daily_data[date] = {'reservations': 0, 'hours': 0, 'revenue': 0}
                    except Exception as e2:
                        print(f"Individual query error for {date}: {e2}")
                        daily_data[date] = {'reservations': 0, 'hours': 0, 'revenue': 0}
        
        # 주별/월별 집계
        labels = []
        reservations_data = []
        hours_data = []
        revenue_data = []
        
        if analysis_type == 'weekly':
            # 주별 집계
            week_data = {}
            for date_str in dates:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                year = date_obj.year
                week = date_obj.isocalendar()[1]
                week_key = f"{year}-W{week:02d}"
                
                if week_key not in week_data:
                    week_data[week_key] = {'reservations': 0, 'hours': 0, 'revenue': 0}
                
                data = daily_data.get(date_str, {'reservations': 0, 'hours': 0, 'revenue': 0})
                week_data[week_key]['reservations'] += data['reservations']
                week_data[week_key]['hours'] += data['hours']
                week_data[week_key]['revenue'] += data['revenue']
            
            # 정렬된 주차별 데이터
            for week_key in sorted(week_data.keys()):
                labels.append(week_key)
                reservations_data.append(week_data[week_key]['reservations'])
                hours_data.append(round(week_data[week_key]['hours'], 1))
                revenue_data.append(week_data[week_key]['revenue'])
                
        elif analysis_type == 'monthly':
            # 월별 집계
            month_data = {}
            for date_str in dates:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                month_key = f"{date_obj.year}-{date_obj.month:02d}"
                
                if month_key not in month_data:
                    month_data[month_key] = {'reservations': 0, 'hours': 0, 'revenue': 0}
                
                data = daily_data.get(date_str, {'reservations': 0, 'hours': 0, 'revenue': 0})
                month_data[month_key]['reservations'] += data['reservations']
                month_data[month_key]['hours'] += data['hours']
                month_data[month_key]['revenue'] += data['revenue']
            
            # 정렬된 월별 데이터
            for month_key in sorted(month_data.keys()):
                labels.append(month_key)
                reservations_data.append(month_data[month_key]['reservations'])
                hours_data.append(round(month_data[month_key]['hours'], 1))
                revenue_data.append(month_data[month_key]['revenue'])
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'labels': labels,
                'reservations': reservations_data,
                'hours': hours_data,
                'revenue': revenue_data,
                'period': f"{start_date} ~ {end_date}",
                'type': analysis_type
            })
        }
        
    except Exception as e:
        print(f"Error in get_trends_data: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
def auto_sync_data():
    """Proxy DB 마지막 날부터 오늘까지 자동 데이터 동기화"""
    try:
        table = dynamodb.Table('studyroom-proxy-db')
        
        # 마지막 데이터 날짜 확인
        response = table.scan(
            ProjectionExpression='#d',
            ExpressionAttributeNames={'#d': 'date'}
        )
        
        if not response['Items']:
            # 데이터가 없으면 최근 7일 수집
            last_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        else:
            # 가장 최근 날짜 찾기
            dates = [item['date'] for item in response['Items']]
            last_date = max(dates)
        
        # 마지막 날부터 오늘까지 수집 (마지막 날 포함)
        start_date = datetime.strptime(last_date, '%Y-%m-%d')
        today = datetime.now()
        
        collected = []
        current = start_date
        
        while current <= today:
            date_str = current.strftime('%Y-%m-%d')
            
            # 새 데이터 수집 (기존 데이터 덮어쓰기)
            result = collect_data_for_date(date_str)
            collected.append(f"{date_str}: {result}")
            current += timedelta(days=1)
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'synced': len(collected),
                'results': collected,
                'last_date': last_date
            })
        }
        
    except Exception as e:
        print(f"Auto sync error: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def collect_data_for_date(target_date):
    """특정 날짜의 데이터 수집"""
    try:
        # 토큰 획득
        token_result = get_new_token()
        if not token_result:
            return "토큰 획득 실패"
        
        token = token_result['access_token']
        p_code = token_result['p_code']
        
        # API 호출 (메인 엔드포인트와 동일한 헤더 사용)
        response = http.request(
            'GET',
            f'https://api.comepass.kr/place/studyroom?date={target_date}',
            headers={
                'Accept': 'application/json, text/plain, */*',
                'Authorization': f'Bearer {token}',
                'Origin': 'https://place.comepass.kr',
                'Referer': 'https://place.comepass.kr/',
                'X-Dmon-Place-Code': p_code,
                'X-Dmon-Request-From': 'place_admin_web',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        
        if response.status != 200:
            print(f"API 호출 실패 - Status: {response.status}")
            print(f"Response headers: {response.headers}")
            print(f"Response data: {response.data.decode('utf-8')}")
            return f"API 호출 실패: {response.status}"
        
        raw_data = json.loads(response.data.decode('utf-8'))
        
        # 예약 데이터 변환 (중복 방지를 위한 정규화)
        reservations = []
        for reservation in raw_data.get('list', []):
            if reservation.get('s_state') in ['USED', 'RESERVED']:
                user_name = reservation.get('m_nm', '')
                if user_name not in ['최은숙', '배준기']:
                    reservations.append({
                        'status': reservation.get('s_state'),
                        'hours': int(reservation.get('s_use_time', 0)),
                        'revenue': int(reservation.get('ord_pay_price', 0)),
                        'room': reservation.get('sg_name', ''),
                        'user': user_name,
                        'start_time': reservation.get('s_s_time', '')
                    })
        
        # DynamoDB 저장 (중복 데이터 덮어쓰기)
        table = dynamodb.Table('studyroom-proxy-db')
        table.put_item(Item={
            'date': target_date,
            'cached_at': datetime.now().isoformat(),
            'full_response': raw_data,
            'reservations': reservations
        })
        
        return f"성공 ({len(reservations)}건)"
        
    except Exception as e:
        return f"오류: {str(e)}"

def collect_and_store_reservation_data():
    """수동 데이터 수집"""
    today = datetime.now().strftime('%Y-%m-%d')
    result = collect_data_for_date(today)
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'message': 'Data collected successfully',
            'date': today,
            'result': result
        })
    }

def collect_past_data():
    """과거 데이터 수집 (12월 전체)"""
    results = []
    
    # 2025년 12월 전체 수집
    for day in range(1, 32):
        date_str = f"2025-12-{day:02d}"
        result = collect_data_for_date(date_str)
        results.append(f"{date_str}: {result}")
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'message': 'Past data collection completed',
            'results': results
        })
    }

def collect_three_months_data():
    """최근 3달간 모든 데이터 수집"""
    results = []
    
    # 2025년 10월 (31일)
    for day in range(1, 32):
        date_str = f"2025-10-{day:02d}"
        result = collect_data_for_date(date_str)
        results.append(f"{date_str}: {result}")
    
    # 2025년 11월 (30일)
    for day in range(1, 31):
        date_str = f"2025-11-{day:02d}"
        result = collect_data_for_date(date_str)
        results.append(f"{date_str}: {result}")
    
    # 2025년 12월 (31일)
    for day in range(1, 32):
        date_str = f"2025-12-{day:02d}"
        result = collect_data_for_date(date_str)
        results.append(f"{date_str}: {result}")
    
    # 2026년 1월 (현재까지)
    for day in range(1, 9):  # 1월 1일~8일
        date_str = f"2026-01-{day:02d}"
        result = collect_data_for_date(date_str)
        results.append(f"{date_str}: {result}")
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'message': 'Three months data collection completed',
            'total_days': len(results),
            'results': results
        })
    }
