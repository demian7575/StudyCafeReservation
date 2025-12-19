# Study Cafe Reservation System - Project Summary

## 프로젝트 개요
Comepass 스터디카페 예약 현황을 실시간으로 조회하는 AWS Lambda 기반 서버리스 애플리케이션

## 시스템 아키텍처

### AWS 서비스 구성
```
API Gateway (refresh-api) 
  ↓
Lambda (refresh-service - Python 3.12)
  ↓
Comepass API + DynamoDB (토큰 캐싱)
```

### 주요 컴포넌트

#### 1. API Gateway
- **ID**: byyksf69t4
- **이름**: refresh-api
- **타입**: REST API (EDGE)
- **엔드포인트**: https://byyksf69t4.execute-api.us-east-1.amazonaws.com/prod/refresh
- **스테이지**: prod
- **리소스**: `/refresh` (GET)
- **통합**: AWS_PROXY → Lambda

#### 2. Lambda Function: refresh-service
- **런타임**: Python 3.12
- **핸들러**: lambda_function.lambda_handler
- **메모리**: 128 MB
- **타임아웃**: 30초
- **역할**: lambda-execution-role
- **환경변수**:
  - `COMEPASS_ID`: 01067898449
  - `COMEPASS_PWD`: 0000

#### 3. DynamoDB
- **테이블**: aipm-backend-prod-stories
- **용도**: 토큰 캐싱 (5분 여유 시간)
- **키**: id (숫자)

## 주요 기능

### 1. 토큰 관리
- DynamoDB에서 캐시된 토큰 조회
- 만료 5분 전 자동 갱신
- Comepass API 로그인 처리

### 2. 예약 현황 조회
- 날짜별 스터디룸 예약 정보 조회
- 3개 룸 지원:
  - 1번 스터디룸 → 2인 오피스룸
  - 2번 스터디룸 → 4인 스터디룸
  - 3번 스터디룸 → 2인 스터디룸

### 3. UI 기능
- **시간 표시**: 00:00 ~ 24:00 (25개 행)
- **가시 행**: 14개 행 동시 표시
- **기본 시작**: 09:00
- **반응형 레이아웃**: 
  - 고정 헤더 (제목)
  - 스크롤 가능한 표 본문
  - 고정 푸터 (날짜 선택, 전일/익일 버튼)
- **모바일 최적화**:
  - 100dvh (동적 뷰포트 높이)
  - Safe area 지원
  - 좌우 스크롤바 제거

### 4. 예약 시간 계산
- 각 예약을 시간 단위로 올림 (Math.ceil)
- 예시:
  - 110분 → 2시간
  - 20분 → 1시간
  - 180분 → 3시간
  - 총합: 6시간

## 배포 정보

### 최근 업데이트 (2025-12-19/20)
**커밋**: e4cbfa3 + 추가 업데이트
**제목**: Fix reservation display and cancellation filtering + REFUND status support

#### 주요 변경사항
1. **24:00 시간대 제거**: 00:00~23:00만 표시 (24시간 정확히)
2. **포괄적인 취소 예약 필터링**:
   - `s_status === 'C'` 또는 `'CANCEL'`
   - `cancel_yn === 'Y'` 또는 `'YES'`
   - `status === 'cancelled'`, `cancelled === true`
   - `is_cancelled === true` 또는 `'Y'`
   - `s_state === 'REFUND'` (환불된 예약)
   - `ord_refund_step === 'SUCCESS'` (환불 완료)
3. **자정 넘어가는 예약 처리**: 전일부터 시작된 예약의 당일 부분만 표시
4. **시간 포맷 일치성**: timeKey와 timeSlots 모두 '00:00' 형식 사용
5. **디버깅 로그 추가**: 예약 데이터 구조 분석 및 취소 예약 스킵 로그
6. **실제 취소 상태 확인**: `s_state: "REFUND"`, `ord_refund_step: "SUCCESS"` 지원

### 배포 명령어
```bash
cd /repo/ebaejun/tools/aws/StudyCafeReservation/refresh-service
python3 -m zipfile -c function.zip lambda_function.py
aws lambda update-function-code \
  --function-name refresh-service \
  --zip-file fileb://function.zip \
  --region us-east-1
```

## GitHub Repository
- **URL**: https://github.com/demian7575/StudyCafeReservation
- **브랜치**: master
- **최근 커밋**: ae37b3a

## 파일 구조
```
refresh-service/
├── lambda_function.py      # 메인 Lambda 함수
├── function.zip            # 배포 패키지
├── README.md              # 기본 문서
├── PROJECT_SUMMARY.md     # 프로젝트 전체 요약 (이 파일)
└── .git/                  # Git 저장소
```

## CSS 레이아웃 상세

### 반응형 디자인
```css
body {
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
}

.header {
  flex-shrink: 0;
  text-align: center;
  padding: 10px;
}

.content {
  flex: 0 0 auto;
}

.spacer {
  flex: 1;  /* 남은 공간 차지 */
}

.footer {
  flex-shrink: 0;
  padding: 10px;
}

.schedule-table tbody {
  max-height: calc(100dvh - 180px);
  overflow-y: auto;
  overflow-x: hidden;
}

.schedule-table tbody tr {
  height: calc((100dvh - 180px) / 14);
}
```

## JavaScript 주요 로직

### 1. 날짜 선택 (Safari 호환)
```javascript
function setDateValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const dateString = year + '-' + month + '-' + day;
  dateInput.value = dateString;
}
```

### 2. 예약 시간 계산
```javascript
const useTimeMinutes = parseInt(reservation.s_use_time);
const useTimeHours = Math.ceil(useTimeMinutes / 60);
roomTotals[roomName] += useTimeHours;
```

### 3. 자동 스크롤 (09:00)
```javascript
setTimeout(() => {
  const tbody = document.querySelector('.schedule-table tbody');
  if (tbody) {
    const rowHeight = tbody.querySelector('tr')?.offsetHeight || 30;
    tbody.scrollTop = 9 * rowHeight;
  }
}, 100);
```

## API 응답 형식

### 성공 응답
```json
{
  "place_name": "장소명",
  "date": "2025-12-18",
  "reservations": {
    "list": [
      {
        "sg_name": "1번 스터디룸",
        "s_s_time": "09:00",
        "s_e_time": "11:00",
        "s_use_time": "120",
        "m_nm": "예약자명"
      }
    ]
  },
  "token_expires": 1734567890,
  "token_cached": true,
  "processing_time": "0.45s"
}
```

## 브라우저 호환성
- Chrome/Edge: 완전 지원
- Safari (iOS): 완전 지원 (100dvh, safe area)
- Firefox: 완전 지원
- 모바일 브라우저: 최적화됨

## 성능 최적화
1. **토큰 캐싱**: DynamoDB 사용으로 API 호출 최소화
2. **전역 변수**: boto3 클라이언트 재사용
3. **비동기 처리**: fetch API 사용
4. **최소 패딩**: 셀 패딩 2px로 축소
5. **동적 높이**: CSS calc()로 계산 최적화

## 보안 고려사항
- 환경변수로 자격증명 관리
- CORS 설정: `Access-Control-Allow-Origin: *`
- API Gateway를 통한 접근 제어
- HTTPS 통신

## 향후 개선 사항
1. 예약자명 클릭 시 상세 정보 표시
2. 예약 추가/수정/삭제 기능
3. 알림 기능 (예약 변경 시)
4. 통계 대시보드
5. 다크 모드 지원
6. 다국어 지원

## 문제 해결

### 아이폰에서 버튼이 안 보이는 경우
- `100dvh` 사용
- `viewport-fit=cover` 설정
- footer에 충분한 padding-bottom

### 스크롤이 작동하지 않는 경우
- tbody에 `display: block` 확인
- `max-height` 설정 확인
- `overflow-y: auto` 확인

### 토큰 만료 오류
- DynamoDB 테이블 접근 권한 확인
- 환경변수 설정 확인
- 토큰 만료 시간 로그 확인

## 연락처
- Repository: https://github.com/demian7575/StudyCafeReservation
- AWS Account: 728378229251
- Region: us-east-1

## 라이선스
Private Repository

---
**마지막 업데이트**: 2025-12-19
**버전**: 1.0.0
