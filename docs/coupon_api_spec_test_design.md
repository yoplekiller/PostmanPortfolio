# Coupon API 테스트 설계 (AI 생성 초안)

`generate_api_tests.py`가 OpenAPI 명세를 읽고 Groq(llama-3.3-70b)로 생성한 테스트케이스 초안입니다. LLM은 테스트 의도(카테고리/조건/기대값)까지만 생성하고, 실행되는 Postman test script(JS)는 파이썬 코드가 결정적으로 컴파일합니다.

## POST /users/{userId}/coupons

| # | 카테고리 | 이름 | 기대 상태코드 | 설명 |
|---|---|---|---|---|
| 1 | 정상 | NormalFlow | 201 | 정상적인 쿠폰 코드 발급 요청 |
| 2 | 경계값 | BoundaryValueShort | 201 | 6자리 쿠폰 코드 발급 요청 |
| 3 | 경계값 | BoundaryValueLong | 201 | 12자리 쿠폰 코드 발급 요청 |
| 4 | 상태전이 | DuplicatedCoupon | 409 | 이미 발급받은 쿠폰 코드 재발급 요청 |
| 5 | 예외처리 | NotFoundCoupon | 404 | 존재하지 않는 쿠폰 코드 발급 요청 |
| 6 | 예외처리 | DuplicatedCouponError | 409 | 이미 발급받은 쿠폰 코드 재발급 요청 |
| 7 | 예외처리 | ExpiredCouponError | 410 | 발급 기간이 지난 쿠폰 코드 발급 요청 |

## POST /coupons/{couponId}/use

| # | 카테고리 | 이름 | 기대 상태코드 | 설명 |
|---|---|---|---|---|
| 1 | 정상 | NormalCouponUsage | 200 | 정상적인 쿠폰 사용 케이스 |
| 2 | 예외처리 | InvalidCouponId | 404 | 존재하지 않은 쿠폰 ID를 사용할 때의 예외처리 케이스 |
| 3 | 예외처리 | UsedCoupon | 409 | 이미 사용된 쿠폰을 사용할 때의 예외처리 케이스 |
| 4 | 예외처리 | ExpiredCoupon | 410 | 만료된 쿠폰을 사용할 때의 예외처리 케이스 |
| 5 | 예외처리 | InsufficientOrderAmount | 400 | 최소 주문 금액 미달인 경우의 예외처리 케이스 |
| 6 | 경계값 | BoundaryOrderAmount | 200 | 최소 주문 금액과 같은 금액인 경우의 경계값 케이스 |
| 7 | 상태전이 | StateTransition | 409 | 이미 사용된 쿠폰을 다시 사용할 때의 상태전이 케이스 |

## GET /coupons/{couponId}

| # | 카테고리 | 이름 | 기대 상태코드 | 설명 |
|---|---|---|---|---|
| 1 | 정상 | CouponStatusRetrieveSuccess | 200 | 정상적인 쿠폰 상태 조회 요청 |
| 2 | 예외처리 | NonExistentCouponRetrieve | 404 | 존재하지 않는 쿠폰 조회 요청 |
| 3 | 상태전이 | CouponStatusRetrieveUsed | 200 | 이미 사용된 쿠폰 상태 조회 요청 |
| 4 | 상태전이 | CouponStatusRetrieveExpired | 200 | 이미 만료된 쿠폰 상태 조회 요청 |

**총 18개 테스트케이스 생성됨** (카테고리: 정상, 경계값, 상태전이, 예외처리)

## 왜 이렇게 만들었는가
- 명세만 넣으면 카테고리별(정상/경계값/상태전이/예외처리) 테스트 초안이 자동으로 나오게 해서, API 스펙이 바뀔 때마다 테스트를 처음부터 다시 설계하지 않고 재생성 후 검토만 하면 되도록 함
- assertion을 LLM이 만든 JS 코드 그대로 실행하지 않고, LLM은 구조화된 의도(JSON)만 만들고 파이썬이 실제 test script로 컴파일 — LLM이 만든 코드를 곧바로 신뢰하지 않고 사람이 검증 가능한 중간 표현을 거치게 한 설계
- 실제 API가 없으므로 각 케이스의 mock_response를 Postman Mock Server 응답으로 등록해 사용 (운영 방식은 DELIVERY_TYPE_MOCK_TEST 컬렉션과 동일)

## 검토 과정에서 발견/수정한 이슈

1. **경로 파라미터 충돌 (수정 완료)**: 같은 엔드포인트의 서로 다른 케이스가 동일한 경로 파라미터 값을
   그대로 써서 URL이 겹치는 경우가 있었음. Postman(Mock Server 포함)은 method+path로 요청을 매칭하므로
   그대로 두면 케이스끼리 충돌함 — `dedupe_path_params()`로 코드 레벨에서 강제 구분하도록 수정.
2. **한자 혼입 (수정 완료)**: LLM 응답에 "쿠폰状态", "已经 만료된" 처럼 한자가 섞여 나온 사례 발견 —
   AutoTC(`src/utils.py`)에서 이미 쓰던 것과 동일한 화이트리스트 정규식 패턴을 `sanitize_case()`로
   추가해 한글/영문/기본 문장부호 외 문자를 제거하도록 수정. 반복 가능한 패턴 오염이라 코드 레벨 가드레일로
   처리(단발성 오타였다면 재생성으로만 대응했을 것).
3. **카테고리 간 시나리오 중복 (알려진 한계, 미수정)**: "POST /users/{userId}/coupons"에서 상태전이
   케이스(#4)와 예외처리 케이스(#6)가 둘 다 "이미 발급받은 쿠폰 재발급"이라는 같은 시나리오를 다룸.
   같은 카테고리 내 중복은 프롬프트로 금지했지만 카테고리 간 중복까지는 막지 않았음 — 두 관점(상태전이/
   예외처리) 다 유효하게 볼 여지가 있어 일단 남겨둠. 완전히 없애려면 엔드포인트 단위로 전체 케이스를
   한 번에 생성(현재는 카테고리 힌트만 주고 LLM이 자체적으로 나눔)하거나, 사후 유사도 검사(AutoTC의
   `dedupe_tc_list`처럼 SequenceMatcher 기반)를 추가해야 함.

**검증**: 위 1·2번 수정 후 로컬 mock 서버 + Newman으로 18 requests / 48 assertions 전부 통과 확인 (2026-07-21).