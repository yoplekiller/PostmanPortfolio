# Coupon API 테스트 설계 (AI 생성 초안)

`generate_api_tests.py`가 OpenAPI 명세를 읽고 Groq(GPT-OSS 120B)로 생성한 테스트케이스 초안입니다. LLM은 테스트 의도(카테고리/조건/기대값)까지만 생성하고, 실행되는 Postman test script(JS)는 파이썬 코드가 결정적으로 컴파일합니다.

## POST /users/{userId}/coupons

| # | 카테고리 | 이름 | 기대 상태코드 | 설명 |
|---|---|---|---|---|
| 1 | 정상 | ValidCoupon | 201 | 유효한 쿠폰 코드로 발급을 성공하는 케이스 |
| 2 | 경계값 | InvalidCouponLength | 404 | 쿠폰 코드의 길이가 qu 경우 발급 실패하는 케이스 |
| 3 | 상태전이 | ExpiredCoupon | 410 | 만료된 쿠폰 코드로 발급신청을 실패하는 케이스 |
| 4 | 예외처리 | AlreadyIssuedCoupon | 409 | 이미 발급받은 쿠폰 코드로 발급신청을 실패하는 케이스 |
| 5 | 예외처리 | NotFoundCoupon | 404 | 존재하지 않는 쿠폰 코드로 발급신청을 실패하는 케이스 |

## POST /coupons/{couponId}/use

| # | 카테고리 | 이름 | 기대 상태코드 | 설명 |
|---|---|---|---|---|
| 1 | 정상 | NormalUsage | 200 | 쿠폰 사용이 정상적으로 처리되는지 검증 |
| 2 | 경계값 | InsufficientOrderAmount | 400 | 최소 주문 금액 미달 시 처리되는지 검증 |
| 3 | 상태전이 | AlreadyUsedCoupon | 409 | 이미 사용된 쿠폰을 사용하려고 할 때 처리되는지 검증 |
| 4 | 예외처리 | NonExistingCoupon | 404 | 존재하지 않는 쿠폰을 사용하려고 할 때 처리되는지 검증 |
| 5 | 예외처리 | ExpiredCoupon | 410 | 만료된 쿠폰을 사용하려고 할 때 처리되는지 검증 |
| 6 | 예외처리 | MinimumOrderAmountNotMet | 400 | 최소 주문 금액 미달 시 처리되는지 검증 |

## GET /coupons/{couponId}

| # | 카테고리 | 이름 | 기대 상태코드 | 설명 |
|---|---|---|---|---|
| 1 | 정상 | NormalGetCoupon | 200 | 쿠폰 상태 조회가 정상적으로 성공하는지를 검증 |
| 2 | 예외처리 | GetCouponNotExist | 404 | 쿠폰이 존재하지 않는 경우 404 응답을 받는지 검증 |
| 3 | 상태전이 | GetCouponStatusUsed | 200 | 이미 사용된 쿠폰의 상태를 조회하는 경우에 대한 응답을 검증 |
| 4 | 상태전이 | GetCouponStatusExpired | 200 | 이미 만료된 쿠폰의 상태를 조회하는 경우에 대한 응답을 검증 |

**총 15개 테스트케이스 생성됨** (카테고리: 정상, 경계값, 상태전이, 예외처리)

## 왜 이렇게 만들었는가
- 명세만 넣으면 카테고리별(정상/경계값/상태전이/예외처리) 테스트 초안이 자동으로 나오게 해서, API 스펙이 바뀔 때마다 테스트를 처음부터 다시 설계하지 않고 재생성 후 검토만 하면 되도록 함
- assertion을 LLM이 만든 JS 코드 그대로 실행하지 않고, LLM은 구조화된 의도(JSON)만 만들고 파이썬이 실제 test script로 컴파일 — LLM이 만든 코드를 곧바로 신뢰하지 않고 사람이 검증 가능한 중간 표현을 거치게 한 설계
- 실제 API가 없으므로 각 케이스의 mock_response를 Postman Mock Server 응답으로 등록해 사용 (운영 방식은 DELIVERY_TYPE_MOCK_TEST 컬렉션과 동일)