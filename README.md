<<<<<<< HEAD
# Postman API Test Portfolio

![Newman API Test](https://github.com/yoplekiller/PostmanPortfolio/actions/workflows/newman-test.yml/badge.svg)
[![View Test Report](https://img.shields.io/badge/Report-View%20Now-blue)](https://yoplekiller.github.io/PostmanPortfolio/report.html)

## 개요

TMDB(영화 데이터베이스) API를 대상으로 Postman Collection을 작성하고, Newman CLI + GitHub Actions로 자동화한 API 테스트 포트폴리오입니다.

## 테스트 구성

| Request | 설명 | 유형 |
|---------|------|------|
| Get Popular Movies | 인기 영화 목록 조회 | 정상 |
| Search Movie | 키워드 검색 결과 확인 | 정상 |
| Get Movie Detail | 특정 영화 상세 정보 조회 | 정상 |
| Invalid API Key | 잘못된 API 키로 401 응답 확인 | 비정상 |
| Not Found Movie | 존재하지 않는 ID로 404 응답 확인 | 비정상 |

## 검증 항목

- 상태 코드 검증 (200 / 401 / 404)
- 응답 필드 존재 여부 확인
- 응답 데이터 타입 검증
- 검색 결과 키워드 포함 여부 확인
- 비정상 케이스 에러 메시지 확인

## 기술 스택

- Postman
- Newman CLI
- newman-reporter-htmlextra
- GitHub Actions (매주 월요일 자동 실행)

## 실행 방법

```bash
npm install -g newman newman-reporter-htmlextra

newman run "MOVIE_API_TEST.postman_collection.json" \
  -e "TMDB ENV.postman_environment.json" \
  --env-var "api_key=YOUR_TMDB_API_KEY" \
  --env-var "movie_id=550" \
  -r htmlextra --reporter-htmlextra-export report.html
```
=======
![Newman API Test](https://github.com/yoplekiller/PostmanPortfolio/actions/workflows/newman-test.yml/badge.svg)
[![View Test Report](https://img.shields.io/badge/Report-View%20Now-blue)](https://yoplekiller.github.io/PostmanPortfolio/report.html)
>>>>>>> efed125efce6c0d38b2079032c69e08b5bd98af8
