# 배달 방식별 API 응답 검증 설계 (Delivery Type Mock API Test Design)

## 배경
"이커머스는 유형별로 다르게 동작한다"는 아이디어를 배달의민족(배민) 도메인으로 구체화한 설계 문서.
실무에서 가게 세팅(오픈/마감 시간 기반) 및 Postman으로 요청값(가게 on/off, 배달방식별 on/off 등)을
직접 확인해본 경험을 기반으로 함.

**실제 배민 API는 로그인/인증이 필요하고 외부 개인이 실서비스에 직접 호출하기 어려우므로,
이 포트폴리오에서는 Postman Mock Server로 응답을 시뮬레이션하고, 그 mock 응답을 Newman으로
검증하는 방식으로 구현한다.** (TMDB 컬렉션이 실제 API를 쓰는 것과 달리, 이 컬렉션은
"설계한 유형 매트릭스를 mock으로 재현하고 검증 로직을 자동화하는 능력"을 보여주는 것이 목적)

---

## 1. 유형 축 정의

| 축 | 값 |
|---|---|
| 배달방식 | 가게배달 / 한집배달 / 알뜰배달 / 픽업 / 매장 |
| 가게 운영상태 | 오픈 / 마감 |

> 확인 필요: 실무 경험 기준으로 가게마다 배달방식을 선택적으로 켜고 끌 수 있는 구조였는지
> (예: `store_delivery: true, baemin1: false, pickup: true` 같은 필드 조합) 기억나는 대로 정리해주시면
> mock 응답 스키마 설계에 바로 반영 가능.

---

## 2. Mock 응답 스키마 (초안)

가게 상세 조회 API 응답이 있다고 가정하고, 배달방식별 on/off 플래그 + 가게 운영상태를 담은 형태로 설계:

```json
{
  "shop_id": "12345",
  "shop_status": "OPEN",           // OPEN | CLOSED
  "delivery_types": {
    "store_delivery": true,        // 가게배달
    "baemin_delivery": false,      // 한집배달
    "saving_delivery": false,      // 알뜰배달
    "pickup": true,                // 픽업
    "dine_in": false               // 매장
  }
}
```

> ⚠️ 실제 필드명/구조는 추측입니다. 실무에서 Postman으로 확인했던 실제 request/response 구조 기억나는 대로
> 알려주시면 스키마를 더 현실적으로 맞출 수 있어요.

---

## 3. 조합별 검증 케이스

| # | shop_status | 배달방식 조합 | 기대 검증 포인트 |
|---|---|---|---|
| 1 | OPEN | store_delivery: true | 주문 가능 상태, 배달비 필드 존재 |
| 2 | CLOSED | store_delivery: true | 배달방식 on이어도 가게 마감이면 주문 불가 응답이어야 함 |
| 3 | OPEN | 전체 delivery_types: false, pickup: true | 픽업만 가능한 응답 구조 확인 |
| 4 | OPEN | 전체 false | 주문 가능한 방식이 하나도 없을 때의 에러/빈 상태 응답 확인 |

*(우선순위 높은 조합부터 Newman 테스트 스크립트로 구현 — TMDB 컬렉션의 "정상/비정상" 구분 패턴과 동일하게
가능한 조합(정상)과 모순되는 조합(마감인데 주문 가능 등, 비정상)을 나눠서 설계)*

---

## 4. 구현 순서 (TODO)

- [x] 2번 mock 응답 스키마 확정 — 실제 필드명은 여전히 추측이나, `shop_status` + `delivery_types(5개 flag)` + `delivery_fee`로 구조 확정하고 `DELIVERY_TYPE_MOCK_TEST.postman_collection.json`에 4개 요청·example로 반영 완료 (2026-07-15)
- [ ] Postman Mock Server 생성 (가게 상태별 응답 여러 개 등록) — **사용자가 Postman 앱에서 직접 해야 하는 유일한 수동 단계.** 컬렉션을 Import → 우클릭 "Mock collection" → 생성된 Mock URL을 `DELIVERY_MOCK_ENV.postman_environment.json`의 `base_url`에 붙여넣기
- [x] Collection 작성 — Request 4개(케이스 1~4)마다 다른 mock 응답(saved example)을 받도록 구성 완료
- [x] Test Script(JS)로 조합별 기대 필드/값 검증 완료 — 상태코드, `delivery_types` 5개 키 존재, `isOrderable` 파생 로직(shop_status + 배달방식 flag) 검증, `delivery_fee` null 처리까지 포함. 로컬 mock 서버로 16개 assertion 전부 통과 확인
- [x] Newman + GitHub Actions 연동 — `newman-test.yml`에 `Run Delivery Type Mock Tests` 스텝 추가 (GitHub secret `DELIVERY_MOCK_URL`이 설정된 경우에만 실행되도록 조건 처리, 미설정 시 기존 TMDB 테스트에는 영향 없음)
- [ ] README에 "왜 mock으로 구현했는가" 설명 추가

---

## 참고
- 검증 방식(계정 세팅 vs API mock)에 대한 일반적 트레이드오프 논의는 KreamQA 프로젝트의
  `docs/transaction_type_test_design.md`에도 같은 패턴으로 정리되어 있음 (크림은 아직 UI 기준 설계).
