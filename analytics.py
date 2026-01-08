import json
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

class StudyRoomAnalytics:
    def __init__(self):
        self.room_mapping = {
            '1번 스터디룸': '2인 오피스룸',
            '2번 스터디룸': '4인 스터디룸', 
            '3번 스터디룸': '2인 스터디룸'
        }
    
    def analyze_reservations(self, reservations_data):
        """예약 데이터 통계 분석"""
        stats = {
            'daily_usage': defaultdict(int),
            'hourly_usage': defaultdict(int),
            'room_usage': defaultdict(int),
            'duration_stats': [],
            'peak_hours': [],
            'utilization_rate': {}
        }
        
        if not reservations_data or not reservations_data.get('list'):
            return self._empty_stats()
        
        for reservation in reservations_data['list']:
            # 취소된 예약 제외
            if self._is_cancelled(reservation):
                continue
            
            # 기본 정보 추출
            room_name = self.room_mapping.get(reservation['sg_name'], reservation['sg_name'])
            start_time = reservation['s_s_time']
            end_time = reservation['s_e_time']
            use_time = int(reservation['s_use_time'])  # 분 단위
            
            # 통계 업데이트
            stats['room_usage'][room_name] += use_time
            stats['duration_stats'].append(use_time)
            
            # 시간대별 사용량
            start_hour = int(start_time.split(':')[0])
            end_hour = int(end_time.split(':')[0])
            
            if end_hour < start_hour:  # 자정 넘어가는 경우
                for hour in range(start_hour, 24):
                    stats['hourly_usage'][hour] += 1
                for hour in range(0, end_hour):
                    stats['hourly_usage'][hour] += 1
            else:
                for hour in range(start_hour, end_hour):
                    stats['hourly_usage'][hour] += 1
        
        return self._calculate_final_stats(stats)
    
    def _is_cancelled(self, reservation):
        """예약 취소 여부 확인"""
        return (reservation.get('s_status') in ['C', 'CANCEL'] or
                reservation.get('cancel_yn') in ['Y', 'YES'] or
                reservation.get('status') == 'cancelled' or
                reservation.get('cancelled') is True or
                reservation.get('is_cancelled') in [True, 'Y'] or
                reservation.get('s_state') == 'REFUND' or
                reservation.get('ord_refund_step') == 'SUCCESS')
    
    def _calculate_final_stats(self, stats):
        """최종 통계 계산"""
        if not stats['duration_stats']:
            return self._empty_stats()
        
        # 피크 시간대 계산
        peak_hours = sorted(stats['hourly_usage'].items(), 
                          key=lambda x: x[1], reverse=True)[:3]
        
        # 이용률 계산 (24시간 기준)
        total_possible_hours = 24 * len(self.room_mapping)
        total_used_hours = sum(stats['room_usage'].values()) / 60
        utilization_rate = (total_used_hours / total_possible_hours) * 100
        
        return {
            'summary': {
                'total_reservations': len(stats['duration_stats']),
                'total_usage_minutes': sum(stats['duration_stats']),
                'total_usage_hours': sum(stats['duration_stats']) / 60,
                'average_duration': statistics.mean(stats['duration_stats']),
                'median_duration': statistics.median(stats['duration_stats']),
                'utilization_rate': round(utilization_rate, 2)
            },
            'room_analysis': {
                room: {
                    'total_minutes': minutes,
                    'total_hours': round(minutes / 60, 2),
                    'percentage': round((minutes / sum(stats['room_usage'].values())) * 100, 2)
                }
                for room, minutes in stats['room_usage'].items()
            },
            'time_analysis': {
                'peak_hours': [{'hour': f"{hour:02d}:00", 'reservations': count} 
                              for hour, count in peak_hours],
                'hourly_distribution': {f"{hour:02d}:00": count 
                                      for hour, count in sorted(stats['hourly_usage'].items())}
            },
            'duration_analysis': {
                'min_duration': min(stats['duration_stats']),
                'max_duration': max(stats['duration_stats']),
                'std_deviation': round(statistics.stdev(stats['duration_stats']) if len(stats['duration_stats']) > 1 else 0, 2)
            }
        }
    
    def _empty_stats(self):
        """빈 통계 반환"""
        return {
            'summary': {
                'total_reservations': 0,
                'total_usage_minutes': 0,
                'total_usage_hours': 0,
                'average_duration': 0,
                'median_duration': 0,
                'utilization_rate': 0
            },
            'room_analysis': {},
            'time_analysis': {'peak_hours': [], 'hourly_distribution': {}},
            'duration_analysis': {'min_duration': 0, 'max_duration': 0, 'std_deviation': 0}
        }

def generate_report(analytics_result):
    """분석 결과 리포트 생성"""
    report = []
    
    # 요약 정보
    summary = analytics_result['summary']
    report.append("=== 스터디룸 예약/사용 통계 분석 ===\n")
    report.append(f"총 예약 건수: {summary['total_reservations']}건")
    report.append(f"총 사용 시간: {summary['total_usage_hours']:.1f}시간")
    report.append(f"평균 사용 시간: {summary['average_duration']:.0f}분")
    report.append(f"전체 이용률: {summary['utilization_rate']}%\n")
    
    # 룸별 분석
    if analytics_result['room_analysis']:
        report.append("=== 룸별 사용 현황 ===")
        for room, data in analytics_result['room_analysis'].items():
            report.append(f"{room}: {data['total_hours']}시간 ({data['percentage']}%)")
        report.append("")
    
    # 시간대별 분석
    if analytics_result['time_analysis']['peak_hours']:
        report.append("=== 피크 시간대 ===")
        for peak in analytics_result['time_analysis']['peak_hours']:
            report.append(f"{peak['hour']}: {peak['reservations']}건")
        report.append("")
    
    return "\n".join(report)

# 사용 예시
if __name__ == "__main__":
    # 샘플 데이터로 테스트
    sample_data = {
        'list': [
            {
                'sg_name': '1번 스터디룸',
                's_s_time': '09:00',
                's_e_time': '12:00',
                's_use_time': '180',
                's_status': 'A',
                'm_nm': '홍길동'
            },
            {
                'sg_name': '2번 스터디룸',
                's_s_time': '14:00',
                's_e_time': '16:00',
                's_use_time': '120',
                's_status': 'A',
                'm_nm': '김철수'
            }
        ]
    }
    
    analytics = StudyRoomAnalytics()
    result = analytics.analyze_reservations(sample_data)
    print(generate_report(result))
