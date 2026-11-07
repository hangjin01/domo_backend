FROM docker.io/library/python:3.11-slim

# 컨테이너 내부 기준 경로입니다. 호스트의 backend 폴더와 이름이 같을 필요는 없습니다.
WORKDIR /app

# PostgreSQL 드라이버 등 네이티브 확장 빌드에 필요한 컴파일러/헤더를 설치합니다.
RUN apt-get update && apt-get install -y gcc libpq-dev

# 의존성 목록을 먼저 복사해 앱 소스만 바뀔 때 패키지 설치 캐시를 재사용합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 단독 이미지 실행의 기본 명령입니다. Compose는 개발용 --reload 명령으로 덮어씁니다.
# 호스트 접속 포트 9000은 docker-compose.yml의 9000:8000 매핑에서 정합니다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
