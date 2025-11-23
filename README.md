# Refresh Service

Comepass 스터디룸 예약 현황을 조회하는 AWS Lambda 함수입니다.

## 기능
- Comepass API를 통한 스터디룸 예약 현황 조회
- DynamoDB를 이용한 토큰 캐싱
- HTML 인터페이스 제공

## 환경변수
- `COMEPASS_ID`: Comepass 로그인 ID
- `COMEPASS_PWD`: Comepass 로그인 비밀번호

## 배포
```bash
zip -r function.zip lambda_function.py
aws lambda update-function-code --function-name refresh-service --zip-file fileb://function.zip
```
