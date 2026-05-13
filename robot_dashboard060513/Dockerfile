# [의도적 비효율 1] 아주 무거운 파이썬 공식 기본 이미지 사용 (약 1GB)
FROM python:3.12

# 작업 디렉토리 설정
WORKDIR /app

# [의도적 비효율 2] 캐시를 활용하지 않고 모든 파일을 한 번에 복사
COPY . /app

# 파이썬 라이브러리 설치
RUN pip install -r requirements.txt

# 포트 개방
EXPOSE 8000

# [의도적 비효율 3] 개발용 서버(app.run)를 그대로 실서비스처럼 실행
CMD ["python", "app.py"]