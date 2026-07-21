# Postman API Test Portfolio

![Newman API Test](https://github.com/yoplekiller/PostmanPortfolio/actions/workflows/newman-test.yml/badge.svg)
[![View Test Report](https://img.shields.io/badge/Report-View%20Now-blue)](https://yoplekiller.github.io/PostmanPortfolio/report.html)

## 개요

Postman Collection을 작성하고 Newman CLI + GitHub Actions로 자동화한 API 테스트 포트폴리오입니다.
① TMDB(영화 데이터베이스) 실제 API 대상 테스트, ② 배달의민족 도메인 기반 유형 매트릭스를
Postman Mock Server로 시뮬레이션한 테스트, 두 개 컬렉션으로 구성되어 있습니다.

## 1. TMDB API 테스트

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

---

## 2. 배달방식 유형 매트릭스 Mock API 테스트

실무(배달의민족)에서 가게 오픈/마감 상태와 배달방식(가게배달/한집배달/알뜰배달/픽업/매장)별 on/off 값을
Postman으로 확인했던 경험을 기반으로, "이커머스는 유형별로 다르게 동작한다"는 설계 관점을 검증한
포트폴리오입니다. 실제 배민 API는 로그인/인증이 필요해 외부에서 직접 호출할 수 없기 때문에,
**Postman Mock Server로 유형별 응답을 시뮬레이션하고 Newman으로 검증**하는 방식을 택했습니다.
(TMDB 컬렉션이 실제 API를 호출하는 것과 달리, 이 컬렉션은 "유형 매트릭스를 설계하고 mock으로
재현·자동검증하는 능력"을 보여주는 것이 목적입니다.)

### 검증 케이스

| # | shop_status | 배달방식 조합 | 검증 포인트 |
|---|---|---|---|
| 1 | OPEN | store_delivery: true | 주문 가능, delivery_fee 필드 존재 |
| 2 | CLOSED | store_delivery: true | 배달방식 flag가 on이어도 가게 마감이면 주문 불가로 판정되어야 함 |
| 3 | OPEN | pickup만 true | 픽업만 가능한 응답 구조 확인, delivery_fee는 null |
| 4 | OPEN | 전체 false | 주문 가능한 방식이 하나도 없는 빈 상태 확인 |

각 요청의 Test Script는 응답 필드 존재 여부뿐 아니라, `shop_status`와 `delivery_types` 값으로
`isOrderable`(주문 가능 여부)을 실제 클라이언트처럼 파생시켜 검증합니다 — 단순 상태코드 체크를 넘어
비즈니스 로직 자체를 테스트로 표현한 부분이 이 컬렉션의 핵심입니다.

자세한 설계 배경은 [`docs/delivery_type_test_design.md`](./docs/delivery_type_test_design.md) 참고.

### 실행 방법

```bash
# Postman에서 DELIVERY_TYPE_MOCK_TEST.postman_collection.json을 Import 후
# 우클릭 "Mock collection"으로 생성한 Mock URL을 base_url로 사용
newman run "DELIVERY_TYPE_MOCK_TEST.postman_collection.json" \
  -e "DELIVERY_MOCK_ENV.postman_environment.json" \
  --env-var "base_url=YOUR_POSTMAN_MOCK_URL" \
  -r htmlextra --reporter-htmlextra-export delivery-report.html
```

CI에서는 GitHub secret `DELIVERY_MOCK_URL`이 설정된 경우에만 이 테스트가 자동 실행됩니다.

---

## 3. OpenAPI 명세 → AI 기반 Postman 테스트케이스 자동 생성

`generate_api_tests.py`에 OpenAPI 명세(YAML/JSON)를 넣으면, 엔드포인트마다 Groq(llama-3.3-70b)가
정상/경계값/상태전이/예외처리 관점의 테스트케이스를 설계하고, Postman 컬렉션(+ mock 응답 + 설계 문서)을
자동 생성합니다.

**설계 포인트 — LLM 산출물을 그대로 실행하지 않음**: LLM은 "테스트 의도"(카테고리, 조건, 기대 응답)까지만
JSON으로 만들고, 실제로 실행되는 Postman test script(JS)는 파이썬 코드가 그 JSON을 결정적으로 컴파일해서
만듭니다. 또한 LLM이 같은 엔드포인트 안에서 서로 다른 케이스에 동일한 경로 파라미터(예: 같은 `userId`)를
중복으로 준 사례가 실제로 있었는데, Postman(및 Mock Server)은 method+path로 요청을 매칭하기 때문에
그대로 두면 여러 테스트케이스가 같은 URL에서 충돌합니다. 이 문제를 프롬프트로 매번 피해가길 기대하는 대신,
`dedupe_path_params()`가 충돌을 감지해 코드 레벨에서 값을 강제로 구분하도록 만들었습니다.

### 예시: Coupon API

샘플 명세 [`openapi/coupon_api_spec.yaml`](./openapi/coupon_api_spec.yaml)(쿠폰 발급/사용/조회, 상태전이+경계값이
있는 도메인)로 실행한 결과 [`COUPON_API_TEST.postman_collection.json`](./COUPON_API_TEST.postman_collection.json) —
3개 엔드포인트에서 17개 테스트케이스가 생성되었고, 로컬 mock 서버로 17 requests / 49 assertions 전부 통과를
확인했습니다. 설계 근거는 [`docs/coupon_api_spec_test_design.md`](./docs/coupon_api_spec_test_design.md) 참고.

### 실행 방법

```bash
pip install -r requirements.txt   # groq, pyyaml, python-dotenv
# .env에 GROQ_API_KEY 설정 (.env.example 참고)
python generate_api_tests.py openapi/coupon_api_spec.yaml

# Postman에서 생성된 컬렉션 Import → Mock Server 생성 → base_url로 사용
newman run "COUPON_API_TEST.postman_collection.json" \
  -e "COUPON_API_MOCK_ENV.postman_environment.json" \
  --env-var "base_url=YOUR_POSTMAN_MOCK_URL"
```

CI에서는 GitHub secret `COUPON_MOCK_URL`이 설정된 경우에만 이 테스트가 자동 실행됩니다.

