import json
import urllib3
import boto3
import os
import time
from datetime import datetime, timedelta

# 전역 변수
dynamodb = boto3.resource('dynamodb')
http = urllib3.PoolManager()

def lambda_handler(event, context):
    start_time = time.time()
    print(f"Lambda started at {datetime.now()}")
    
    if event is None:
        event = {}
    
    # 벌크 데이터 수집
    if event.get('path') == '/api/bulk-collect':
        return bulk_collect_data()
    
    # 추이 분석 API
    if event.get('path') == '/api/trends':
        query_params = event.get('queryStringParameters') or {}
        analysis_type = query_params.get('type', 'daily')
        start_date = query_params.get('start', '')
        end_date = query_params.get('end', '')
        return get_trends_from_proxy(analysis_type, start_date, end_date)
    
    # 통계 분석 API
    if event.get('path') == '/api/analytics':
        query_params = event.get('queryStringParameters') or {}
        analysis_type = query_params.get('type', 'daily')
        period = query_params.get('period', '')
        return get_analytics_from_proxy(analysis_type, period)
    
    # 추이 분석 페이지
    if event.get('path') == '/trends':
        return serve_trends_page()
    
    # 통계 분석 페이지
    if event.get('path') == '/analytics' or event.get('queryStringParameters', {}).get('view') == 'analytics':
        return serve_analytics_page()
    
    # 기본 페이지
    return {
        'statusCode': 302,
        'headers': {'Location': '/analytics'},
        'body': ''
    }

def get_comepass_token():
    """Comepass API 토큰 가져오기"""
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    login_data = {"id": comepass_id, "pwd": comepass_pwd}
    login_response = http.request('POST', login_url, body=json.dumps(login_data), headers=login_headers)
    result = json.loads(login_response.data.decode('utf-8'))
    
    if result.get('result') == 'success':
        return result['access_token'], result['p_code']
    else:
        raise Exception(f'로그인 실패: {result.get("message", "Unknown error")}')

def bulk_collect_data():
    """과거 60일 데이터 수집"""
    try:
        access_token, p_code = get_comepass_token()
        table = dynamodb.Table('studyroom-proxy-db')
        
        success_count = 0
        end_date = datetime.now()
        
        for i in range(60):
            current_date = end_date - timedelta(days=i)
            date_str = current_date.strftime('%Y-%m-%d')
            
            try:
                # Comepass API 호출
                url = f'https://api.comepass.kr/place/studyroom?date={date_str}'
                headers = {
                    'Accept': 'application/json, text/plain, */*',
                    'Authorization': f'Bearer {access_token}',
                    'Origin': 'https://place.comepass.kr',
                    'Referer': 'https://place.comepass.kr/',
                    'X-Dmon-Place-Code': p_code,
                    'X-Dmon-Request-From': 'place_admin_web',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                response = http.request('GET', url, headers=headers)
                data = json.loads(response.data.decode('utf-8'))
                
                # 전체 응답을 저장
                table.put_item(Item={
                    'date': date_str,
                    'full_response': data,
                    'cached_at': int(datetime.now().timestamp())
                })
                
                success_count += 1
                record_count = len(data.get('list', []))
                print(f"Saved {date_str}: {record_count} records")
                
            except Exception as e:
                print(f"Error processing {date_str}: {e}")
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'success': True, 'processed_days': success_count})
        }
        
    except Exception as e:
        print(f"Error in bulk_collect_data: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
def get_trends_from_proxy(analysis_type, start_date, end_date):
    """프록시 DB에서 추이 데이터 조회"""
    try:
        table = dynamodb.Table('studyroom-proxy-db')
        
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        # 일별 데이터 수집
        daily_data = {}
        current_date = start
        while current_date <= end:
            date_str = current_date.strftime('%Y-%m-%d')
            
            try:
                response = table.get_item(Key={'date': date_str})
                if 'Item' in response and 'full_response' in response['Item']:
                    full_data = response['Item']['full_response']
                    reservations = full_data.get('list', [])
                    
                    # 취소되지 않은 예약만 필터링
                    active_reservations = [r for r in reservations if r.get('s_state') not in ['REFUND', 'CANCEL']]
                    
                    daily_data[date_str] = {
                        'reservations': len(active_reservations),
                        'revenue': sum(int(r.get('ord_pay_price', 0)) for r in active_reservations),
                        'hours': sum(int(r.get('s_use_time', 0)) for r in active_reservations) / 60.0
                    }
                else:
                    daily_data[date_str] = {'reservations': 0, 'revenue': 0, 'hours': 0.0}
            except Exception as e:
                print(f"Error getting data for {date_str}: {e}")
                daily_data[date_str] = {'reservations': 0, 'revenue': 0, 'hours': 0.0}
            
            current_date += timedelta(days=1)
        
        # 분석 타입에 따라 집계
        trends = []
        if analysis_type == 'daily':
            for date_str, data in daily_data.items():
                trends.append({
                    'period': date_str,
                    'reservations': data['reservations'],
                    'revenue': data['revenue'],
                    'hours': round(data['hours'], 1)
                })
        elif analysis_type == 'weekly':
            weekly_data = {}
            for date_str, data in daily_data.items():
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                year, week, _ = date_obj.isocalendar()
                week_key = f"{year}-W{week:02d}"
                
                if week_key not in weekly_data:
                    weekly_data[week_key] = {'reservations': 0, 'revenue': 0, 'hours': 0.0}
                
                weekly_data[week_key]['reservations'] += data['reservations']
                weekly_data[week_key]['revenue'] += data['revenue']
                weekly_data[week_key]['hours'] += data['hours']
            
            for week_key, data in sorted(weekly_data.items()):
                trends.append({
                    'period': week_key,
                    'reservations': data['reservations'],
                    'revenue': data['revenue'],
                    'hours': round(data['hours'], 1)
                })
        else:  # monthly
            monthly_data = {}
            for date_str, data in daily_data.items():
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                month_key = date_obj.strftime('%Y-%m')
                
                if month_key not in monthly_data:
                    monthly_data[month_key] = {'reservations': 0, 'revenue': 0, 'hours': 0.0}
                
                monthly_data[month_key]['reservations'] += data['reservations']
                monthly_data[month_key]['revenue'] += data['revenue']
                monthly_data[month_key]['hours'] += data['hours']
            
            for month_key, data in sorted(monthly_data.items()):
                trends.append({
                    'period': month_key,
                    'reservations': data['reservations'],
                    'revenue': data['revenue'],
                    'hours': round(data['hours'], 1)
                })
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'trends': trends})
        }
        
    except Exception as e:
        print(f"Error in get_trends_from_proxy: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }

def get_analytics_from_proxy(analysis_type, period):
    """프록시 DB에서 통계 데이터 조회"""
    try:
        table = dynamodb.Table('studyroom-proxy-db')
        
        # 기본값 설정
        if not period:
            today = datetime.now()
            if analysis_type == 'daily':
                period = today.strftime('%Y-%m-%d')
            elif analysis_type == 'weekly':
                year, week, _ = today.isocalendar()
                period = f"{year}-W{week:02d}"
            else:  # monthly
                period = today.strftime('%Y-%m')
        
        # 데이터 수집
        all_reservations = []
        
        if analysis_type == 'daily':
            response = table.get_item(Key={'date': period})
            if 'Item' in response and 'full_response' in response['Item']:
                all_reservations = response['Item']['full_response'].get('list', [])
        elif analysis_type == 'weekly':
            year, week = period.split('-W')
            week_start = datetime.strptime(f'{year}-W{week}-1', '%Y-W%W-%w')
            for i in range(7):
                date_str = (week_start + timedelta(days=i)).strftime('%Y-%m-%d')
                response = table.get_item(Key={'date': date_str})
                if 'Item' in response and 'full_response' in response['Item']:
                    all_reservations.extend(response['Item']['full_response'].get('list', []))
        else:  # monthly
            year, month = period.split('-')
            days_in_month = 31 if int(month) in [1,3,5,7,8,10,12] else 30 if int(month) != 2 else 29 if int(year) % 4 == 0 else 28
            
            for day in range(1, days_in_month + 1):
                date_str = f"{year}-{month.zfill(2)}-{str(day).zfill(2)}"
                response = table.get_item(Key={'date': date_str})
                if 'Item' in response and 'full_response' in response['Item']:
                    all_reservations.extend(response['Item']['full_response'].get('list', []))
        
        # 취소되지 않은 예약만 필터링
        active_reservations = [r for r in all_reservations if r.get('s_state') not in ['REFUND', 'CANCEL']]
        
        # 통계 계산
        total_reservations = len(active_reservations)
        total_revenue = sum(int(r.get('ord_pay_price', 0)) for r in active_reservations)
        total_hours = sum(int(r.get('s_use_time', 0)) for r in active_reservations) / 60.0
        avg_duration = (sum(int(r.get('s_use_time', 0)) for r in active_reservations) / len(active_reservations)) if active_reservations else 0
        
        # 룸별 분석
        room_usage = {}
        for r in active_reservations:
            room = r.get('pv_name', 'Unknown')
            hours = int(r.get('s_use_time', 0)) / 60.0
            room_usage[room] = room_usage.get(room, 0) + hours
        
        room_analysis = {}
        if room_usage:
            total_room_hours = sum(room_usage.values())
            for room, hours in room_usage.items():
                room_analysis[room] = {
                    'total_hours': round(hours, 1),
                    'percentage': round((hours / total_room_hours) * 100, 2) if total_room_hours > 0 else 0
                }
        
        # 시간대별 분석
        hour_usage = {}
        for r in active_reservations:
            start_time = r.get('s_s_time', '00:00:00')
            hour = start_time.split(':')[0] + ':00'
            hour_usage[hour] = hour_usage.get(hour, 0) + 1
        
        peak_hours = [{'hour': hour, 'reservations': count} for hour, count in sorted(hour_usage.items(), key=lambda x: x[1], reverse=True)[:5]]
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'summary': {
                    'total_reservations': total_reservations,
                    'total_revenue': total_revenue,
                    'total_usage_hours': round(total_hours, 1),
                    'average_duration': round(avg_duration, 2)
                },
                'room_analysis': room_analysis,
                'time_analysis': {
                    'peak_hours': peak_hours
                }
            })
        }
        
    except Exception as e:
        print(f"Error in get_analytics_from_proxy: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
def serve_trends_page():
    """추이 분석 페이지"""
    html = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>스터디카페 추이분석</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f8f9fa; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .nav { margin: 20px 0; }
        .nav-btn { background: #007bff; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin: 0 5px; }
        .nav-btn:hover { background: #0056b3; }
        .controls { margin: 20px 0; text-align: center; }
        .period-btn { background: #6c757d; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin: 0 5px; }
        .period-btn.active { background: #007bff; }
        .period-btn:hover { opacity: 0.8; }
        .chart-container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .loading { text-align: center; padding: 50px; }
        input[type="date"] { padding: 8px; margin: 0 10px; border: 1px solid #ddd; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>스터디카페 추이분석</h1>
            <div class="nav">
                <button onclick="location.href='/analytics'" class="nav-btn">통계분석</button>
                <button onclick="location.href='/trends'" class="nav-btn">추이분석</button>
            </div>
        </div>
        
        <div class="controls">
            <button class="period-btn active" onclick="switchType('daily')">일별</button>
            <button class="period-btn" onclick="switchType('weekly')">주별</button>
            <button class="period-btn" onclick="switchType('monthly')">월별</button>
            
            <input type="date" id="startDate" onchange="loadTrends()">
            <input type="date" id="endDate" onchange="loadTrends()">
            <button onclick="loadTrends()" class="nav-btn">조회</button>
        </div>
        
        <div id="trends-content" class="loading">
            <p>추이 데이터를 불러오는 중...</p>
        </div>
    </div>

    <script>
        let currentType = 'daily';
        
        function switchType(type) {
            currentType = type;
            
            document.querySelectorAll('.period-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            // 기본 날짜 설정: 2달 전부터 오늘까지
            const endDate = new Date();
            const startDate = new Date();
            startDate.setMonth(endDate.getMonth() - 2);
            
            document.getElementById('startDate').value = startDate.toISOString().split('T')[0];
            document.getElementById('endDate').value = endDate.toISOString().split('T')[0];
            
            setTimeout(() => loadTrends(), 100);
        }
        
        function loadTrends() {
            const startDate = document.getElementById('startDate').value;
            const endDate = document.getElementById('endDate').value;
            
            if (!startDate || !endDate) return;
            
            document.getElementById('trends-content').innerHTML = '<div class="loading"><p>추이 데이터를 불러오는 중...</p></div>';
            
            fetch(`/prod/api/trends?type=${currentType}&start=${startDate}&end=${endDate}`)
                .then(response => response.json())
                .then(data => displayTrends(data))
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('trends-content').innerHTML = '<div class="loading"><p>데이터 로드 중 오류가 발생했습니다.</p></div>';
                });
        }
        
        function displayTrends(data) {
            const content = document.getElementById('trends-content');
            
            content.innerHTML = `
                <div class="chart-grid">
                    <div class="chart-container">
                        <h3>매출 추이</h3>
                        <canvas id="revenueChart"></canvas>
                    </div>
                    <div class="chart-container">
                        <h3>예약 건수 추이</h3>
                        <canvas id="reservationChart"></canvas>
                    </div>
                </div>
                <div class="chart-container">
                    <h3>사용 시간 추이</h3>
                    <canvas id="hoursChart"></canvas>
                </div>
            `;
            
            const labels = data.trends.map(t => t.period);
            const revenues = data.trends.map(t => t.revenue);
            const reservations = data.trends.map(t => t.reservations);
            const hours = data.trends.map(t => t.hours);
            
            // 매출 차트
            new Chart(document.getElementById('revenueChart'), {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '매출 (원)',
                        data: revenues,
                        borderColor: '#007bff',
                        backgroundColor: 'rgba(0, 123, 255, 0.1)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function(value) {
                                    return value.toLocaleString() + '원';
                                }
                            }
                        }
                    }
                }
            });
            
            // 예약 건수 차트
            new Chart(document.getElementById('reservationChart'), {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '예약 건수',
                        data: reservations,
                        backgroundColor: '#28a745',
                        borderColor: '#28a745',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function(value) {
                                    return value + '건';
                                }
                            }
                        }
                    }
                }
            });
            
            // 사용 시간 차트
            new Chart(document.getElementById('hoursChart'), {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '사용 시간',
                        data: hours,
                        borderColor: '#ffc107',
                        backgroundColor: 'rgba(255, 193, 7, 0.1)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function(value) {
                                    return value.toFixed(1) + '시간';
                                }
                            }
                        }
                    }
                }
            });
        }
        
        window.onload = () => switchType('daily');
    </script>
</body>
</html>'''
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': html
    }

def serve_analytics_page():
    """통계 분석 페이지"""
    html = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>스터디카페 통계분석</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f8f9fa; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .nav { margin: 20px 0; }
        .nav-btn { background: #007bff; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin: 0 5px; }
        .nav-btn:hover { background: #0056b3; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-card h3 { margin: 0 0 15px 0; color: #333; }
        .stat-number { font-size: 2em; font-weight: bold; color: #007bff; }
        .chart-container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .loading { text-align: center; padding: 50px; }
        .period-selector { margin: 20px 0; text-align: center; }
        .period-btn { background: #6c757d; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin: 0 5px; }
        .period-btn.active { background: #007bff; }
        .period-btn:hover { opacity: 0.8; }
        select { padding: 8px; margin: 0 5px; border: 1px solid #ddd; border-radius: 4px; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>스터디카페 통계분석</h1>
            <div class="nav">
                <button onclick="location.href='/analytics'" class="nav-btn">통계분석</button>
                <button onclick="location.href='/trends'" class="nav-btn">추이분석</button>
            </div>
        </div>
        
        <div class="period-selector">
            <div class="period-controls">
                <select id="dateSelector" onchange="loadAnalytics('daily')">
                    <option value="">날짜 선택</option>
                </select>
                <select id="weekSelector" onchange="loadAnalytics('weekly')" style="display:none">
                    <option value="">주 선택</option>
                </select>
                <select id="monthSelector" onchange="loadAnalytics('monthly')" style="display:none">
                    <option value="">월 선택</option>
                </select>
            </div>
            <div class="type-buttons">
                <button class="period-btn active" onclick="switchType('daily')">일별</button>
                <button class="period-btn" onclick="switchType('weekly')">주별</button>
                <button class="period-btn" onclick="switchType('monthly')">월별</button>
            </div>
        </div>
        
        <div id="analytics-content" class="loading">
            <p>통계 데이터를 불러오는 중...</p>
        </div>
    </div>

    <script>
        let currentType = 'daily';
        
        function switchType(type) {
            currentType = type;
            
            document.querySelectorAll('.period-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            // 선택기 표시/숨김
            document.getElementById('dateSelector').style.display = type === 'daily' ? 'inline' : 'none';
            document.getElementById('weekSelector').style.display = type === 'weekly' ? 'inline' : 'none';
            document.getElementById('monthSelector').style.display = type === 'monthly' ? 'inline' : 'none';
            
            // 옵션 생성 및 기본값 설정
            if (type === 'daily') {
                populateDateOptions();
                const today = new Date().toISOString().split('T')[0];
                document.getElementById('dateSelector').value = today;
                setTimeout(() => loadAnalytics('daily'), 100);
            } else if (type === 'weekly') {
                populateWeekOptions();
                const today = new Date();
                const weekStr = `${today.getFullYear()}-W${getWeekNumber(today)}`;
                document.getElementById('weekSelector').value = weekStr;
                setTimeout(() => loadAnalytics('weekly'), 100);
            } else {
                populateMonthOptions();
                const today = new Date();
                const monthStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
                document.getElementById('monthSelector').value = monthStr;
                setTimeout(() => loadAnalytics('monthly'), 100);
            }
        }
        
        function populateDateOptions() {
            const select = document.getElementById('dateSelector');
            select.innerHTML = '<option value="">날짜 선택</option>';
            
            for (let i = 0; i < 30; i++) {
                const date = new Date();
                date.setDate(date.getDate() - i);
                const dateStr = date.toISOString().split('T')[0];
                const option = document.createElement('option');
                option.value = dateStr;
                option.textContent = dateStr;
                select.appendChild(option);
            }
        }
        
        function populateWeekOptions() {
            const select = document.getElementById('weekSelector');
            select.innerHTML = '<option value="">주 선택</option>';
            
            for (let i = 0; i < 12; i++) {
                const date = new Date();
                date.setDate(date.getDate() - (i * 7));
                const weekStr = `${date.getFullYear()}-W${getWeekNumber(date)}`;
                const option = document.createElement('option');
                option.value = weekStr;
                option.textContent = `${weekStr} (${date.toISOString().split('T')[0]})`;
                select.appendChild(option);
            }
        }
        
        function populateMonthOptions() {
            const select = document.getElementById('monthSelector');
            select.innerHTML = '<option value="">월 선택</option>';
            
            for (let i = 0; i < 12; i++) {
                const date = new Date();
                date.setMonth(date.getMonth() - i);
                const monthStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
                const option = document.createElement('option');
                option.value = monthStr;
                option.textContent = monthStr;
                select.appendChild(option);
            }
        }
        
        function getWeekNumber(date) {
            const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
            const dayNum = d.getUTCDay() || 7;
            d.setUTCDate(d.getUTCDate() + 4 - dayNum);
            const yearStart = new Date(Date.UTC(d.getUTCFullYear(),0,1));
            return Math.ceil((((d - yearStart) / 86400000) + 1)/7);
        }
        
        function loadAnalytics(type) {
            let period = '';
            if (type === 'daily') {
                period = document.getElementById('dateSelector').value;
            } else if (type === 'weekly') {
                period = document.getElementById('weekSelector').value;
            } else {
                period = document.getElementById('monthSelector').value;
            }
            
            if (!period) return;
            
            document.getElementById('analytics-content').innerHTML = '<div class="loading"><p>통계 데이터를 불러오는 중...</p></div>';
            
            fetch(`/prod/api/analytics?type=${type}&period=${period}`)
                .then(response => response.json())
                .then(data => displayAnalytics(data))
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('analytics-content').innerHTML = '<div class="loading"><p>데이터 로드 중 오류가 발생했습니다.</p></div>';
                });
        }
        
        function displayAnalytics(data) {
            const content = document.getElementById('analytics-content');
            
            let html = `
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3>총 예약 건수</h3>
                        <div class="stat-number">${data.summary.total_reservations}</div>
                    </div>
                    <div class="stat-card">
                        <h3>총 매출</h3>
                        <div class="stat-number">${data.summary.total_revenue.toLocaleString()}</div>
                        <p>원</p>
                    </div>
                    <div class="stat-card">
                        <h3>총 사용 시간</h3>
                        <div class="stat-number">${data.summary.total_usage_hours.toFixed(1)}</div>
                        <p>시간</p>
                    </div>
                    <div class="stat-card">
                        <h3>평균 사용 시간</h3>
                        <div class="stat-number">${data.summary.average_duration.toFixed(0)}</div>
                        <p>분</p>
                    </div>
                </div>`;
            
            if (Object.keys(data.room_analysis).length > 0) {
                html += `
                    <div class="chart-container">
                        <h3>룸별 사용 현황</h3>
                        <table>
                            <thead>
                                <tr><th>룸 이름</th><th>사용 시간</th><th>비율</th></tr>
                            </thead>
                            <tbody>`;
                
                Object.entries(data.room_analysis).forEach(([room, stats]) => {
                    html += `<tr><td>${room}</td><td>${stats.total_hours}시간</td><td>${stats.percentage}%</td></tr>`;
                });
                
                html += `</tbody></table></div>`;
            }
            
            if (data.time_analysis.peak_hours.length > 0) {
                html += `
                    <div class="chart-container">
                        <h3>피크 시간대</h3>
                        <table>
                            <thead>
                                <tr><th>시간</th><th>예약 건수</th></tr>
                            </thead>
                            <tbody>`;
                
                data.time_analysis.peak_hours.forEach(peak => {
                    html += `<tr><td>${peak.hour}</td><td>${peak.reservations}건</td></tr>`;
                });
                
                html += `</tbody></table></div>`;
            }
            
            content.innerHTML = html;
        }
        
        window.onload = () => {
            switchType('daily');
        };
    </script>
</body>
</html>'''
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': html
    }
