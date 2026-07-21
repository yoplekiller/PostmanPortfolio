"""
OpenAPI 명세 → Postman 테스트케이스 자동 생성

엔드포인트별로 Groq LLM에게 정상/경계값/상태전이/예외처리 관점의 테스트케이스를
구조화된 JSON으로 받아온 뒤, assertion은 파이썬에서 결정적으로 Postman test script(JS)로
컴파일한다. LLM 출력은 "테스트 의도(구조화 데이터)"까지만 담당하고, 실행 가능한 코드 생성은
코드가 담당하는 구조 — LLM이 만든 JS를 그대로 실행하는 것보다 안전하다.

사용법:
  python generate_api_tests.py openapi/coupon_api_spec.yaml
"""

import sys
import io
import os
import re
import json
import uuid
import time
import argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import yaml
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODEL = "llama-3.3-70b-versatile"

CATEGORY_GUIDE = {
    "정상": "명세대로 정상 흐름이 성공하는 케이스",
    "경계값": "숫자·문자 길이 등 경계값 바로 위/아래를 다루는 케이스 (해당 없으면 생략)",
    "상태전이": "리소스 상태(발급됨/사용됨/만료됨 등)가 이미 바뀐 뒤 재요청하는 케이스 (해당 없으면 생략)",
    "예외처리": "명세에 정의된 4xx 응답마다 1개씩",
}

STATUS_TEXT = {
    200: "OK", 201: "Created", 204: "No Content",
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
    404: "Not Found", 409: "Conflict", 410: "Gone", 422: "Unprocessable Entity",
}

_FIELD_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$")

# AI 응답에 가끔 섞이는 한자 오염 방지 (AutoTC src/utils.py sanitize()와 동일한 패턴)
_FOREIGN_SCRIPT_PATTERN = re.compile(r"[^\x20-\x7E가-힣ㄱ-ㅎㅏ-ㅣ₩\t\n\r]+")


def _sanitize_text(value):
    if not isinstance(value, str):
        return value
    if _FOREIGN_SCRIPT_PATTERN.search(value):
        value = _FOREIGN_SCRIPT_PATTERN.sub("", value)
        value = re.sub(r"[ \t]{2,}", " ", value).strip()
    return value


def sanitize_case(case: dict) -> dict:
    for field in ("name", "category", "description"):
        if field in case:
            case[field] = _sanitize_text(case[field])
    return case


# ── OpenAPI 파싱 ─────────────────────────────────────────────────────

def load_spec(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        if path.endswith((".yaml", ".yml")):
            return yaml.safe_load(f)
        return json.load(f)


def iter_endpoints(spec: dict):
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            yield path, method.upper(), op


def endpoint_context(path: str, method: str, op: dict) -> str:
    lines = [f"{method} {path}", f"설명: {op.get('description') or op.get('summary', '')}"]
    params = op.get("parameters", [])
    if params:
        lines.append("경로 파라미터: " + ", ".join(p["name"] for p in params))
    body_schema = (
        op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
    )
    if body_schema:
        lines.append("요청 바디 스키마: " + json.dumps(body_schema, ensure_ascii=False))
    resp_lines = []
    for code, resp in op.get("responses", {}).items():
        resp_lines.append(f"  {code}: {resp.get('description', '')}")
        schema = resp.get("content", {}).get("application/json", {}).get("schema")
        if schema:
            resp_lines.append(f"    응답 스키마: {json.dumps(schema, ensure_ascii=False)}")
    lines.append("응답:\n" + "\n".join(resp_lines))
    return "\n".join(lines)


# ── Groq 호출 ────────────────────────────────────────────────────────

def call_groq_for_cases(client: Groq, path: str, method: str, op: dict) -> list:
    ctx = endpoint_context(path, method, op)
    prompt = f"""아래 API 엔드포인트에 대한 Postman 테스트케이스를 설계하세요.

[엔드포인트 명세]
{ctx}

[카테고리 가이드 — 해당사항 없는 카테고리는 생략 가능, 있으면 반드시 포함]
{json.dumps(CATEGORY_GUIDE, ensure_ascii=False, indent=2)}

각 테스트케이스는 아래 JSON 스키마를 따르세요. 마크다운 없이 JSON 배열만 출력:
[
  {{
    "name": "영문 짧은 테스트 이름 (Postman request 이름)",
    "category": "정상|경계값|상태전이|예외처리",
    "description": "이 케이스가 검증하는 것을 한국어 한 문장으로",
    "path_params": {{"경로파라미터명": "구체적인 값"}},
    "body": {{"필드명": "값"}},
    "expected_status": 정수,
    "mock_response": {{"expected_status와 논리적으로 일치하는 구체적인 응답 JSON"}},
    "assertions": [
      {{"field": "mock_response 안의 실제 키 (dot 표기 가능, 예: data.status)", "op": "eq|exists|type|gte|lte", "value": "eq/gte/lte는 값, type은 string|number|boolean"}}
    ]
  }}
]

규칙:
- mock_response는 expected_status와 반드시 논리적으로 일치 (4xx면 성공 응답 필드를 넣지 말 것 — {{"error": "설명"}} 정도로 충분)
- assertions.field는 mock_response에 실제로 존재하는 키만 사용, 점(.) 표기는 실제 중첩 구조와 일치해야 함
- path_params 키는 명세의 경로 파라미터 이름과 정확히 일치
- GET 요청에는 "body" 생략
- 같은 카테고리 안에서도 서로 다른 시나리오여야 함 (중복 금지)
"""

    response = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 API 테스트 설계를 전문으로 하는 시니어 QA 엔지니어입니다. "
                            "OpenAPI 명세를 읽고 정상/경계값/상태전이/예외처리 관점에서 빠짐없이 "
                            "테스트케이스를 설계합니다. 지정된 JSON 스키마만 출력하고 다른 설명은 "
                            "붙이지 않습니다. 필드명·설명은 한국어, name(테스트 이름)만 영문으로 "
                            "작성하세요."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4000,
            )
            break
        except Exception as e:
            e_str = str(e).lower()
            if "per day" in e_str or "tpd" in e_str:
                raise RuntimeError("Groq 일일 토큰 한도 초과 — 내일 다시 시도하세요") from e
            if "rate_limit" in e_str or "429" in str(e):
                wait = 65 * (attempt + 1)
                print(f"    [Rate Limit] {wait}초 대기 후 재시도...")
                time.sleep(wait)
            else:
                raise

    if response is None:
        print(f"    [오류] {method} {path} — Rate Limit 재시도 소진, 건너뜀")
        return []

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        last_brace = raw.rfind("},")
        if last_brace == -1:
            last_brace = raw.rfind("}")
        if last_brace > 0:
            recovered = raw[: last_brace + 1].rstrip(",") + "\n]"
            try:
                result = json.loads(recovered if recovered.startswith("[") else "[" + recovered)
                print(f"    [복구] JSON 잘림 감지 — {len(result)}개 복구됨")
                return result
            except json.JSONDecodeError:
                pass
        print(f"    [경고] JSON 파싱 실패 (응답 앞부분: {raw[:200]}...)")
        return []


# ── Postman test script 컴파일 (결정적, LLM 산출물 그대로 실행 안 함) ──

def compile_test_script(expected_status: int, assertions: list) -> list:
    lines = ["let jsonData = pm.response.json();", ""]
    lines.append(f'pm.test("Status is {expected_status}", function () {{')
    lines.append(f"    pm.response.to.have.status({expected_status});")
    lines.append("});")

    for a in assertions or []:
        field = a.get("field", "")
        op = a.get("op", "")
        value = a.get("value")
        if not _FIELD_PATTERN.match(field):
            lines.append(f"\n// [건너뜀] 허용되지 않는 field 표기: {field!r}")
            continue

        test_name = json.dumps(f"{field} {op} {value if value is not None else ''}".strip(), ensure_ascii=False)
        accessor = f"jsonData.{field}"
        lines.append("")
        lines.append(f"pm.test({test_name}, function () {{")
        if op == "exists":
            lines.append(f'    pm.expect(jsonData).to.have.nested.property({json.dumps(field)});')
        elif op == "eq":
            lines.append(f"    pm.expect({accessor}).to.eql({json.dumps(value, ensure_ascii=False)});")
        elif op == "type":
            lines.append(f'    pm.expect({accessor}).to.be.a({json.dumps(value)});')
        elif op == "gte":
            lines.append(f"    pm.expect({accessor}).to.be.at.least({json.dumps(value)});")
        elif op == "lte":
            lines.append(f"    pm.expect({accessor}).to.be.at.most({json.dumps(value)});")
        else:
            lines.append(f"    // 알 수 없는 op: {op!r} — 수동 확인 필요")
        lines.append("});")

    return lines


# ── Postman collection 조립 ──────────────────────────────────────────

def build_url(path: str, path_params: dict) -> tuple:
    resolved = path
    for k, v in (path_params or {}).items():
        resolved = resolved.replace("{" + k + "}", str(v))
    segments = [s for s in resolved.strip("/").split("/") if s]
    return f"{{{{base_url}}}}{resolved}", segments


def dedupe_path_params(path: str, cases: list) -> list:
    """Postman(Mock Server 포함)은 method+path로 요청을 매칭하므로, 같은 엔드포인트 안에서
    path_params가 겹치는 케이스가 있으면 뒤쪽 케이스의 값을 강제로 구분해 URL 충돌을 막는다.
    LLM이 매번 서로 다른 id를 주도록 프롬프트에 기대는 대신, 코드가 유일성을 보장한다."""
    seen = set()
    for idx, case in enumerate(cases, start=1):
        params = case.get("path_params") or {}
        url, _ = build_url(path, params)
        if url in seen and params:
            params = {k: f"{v}-C{idx}" for k, v in params.items()}
            case["path_params"] = params
            url, _ = build_url(path, params)
        seen.add(url)
    return cases


def build_request_item(path: str, method: str, case: dict, case_idx: int) -> dict:
    url_raw, segments = build_url(path, case.get("path_params", {}))
    expected_status = case.get("expected_status", 200)
    mock_response = case.get("mock_response", {})

    request = {
        "method": method,
        "header": [],
        "url": {"raw": url_raw, "host": ["{{base_url}}"], "path": segments},
        "description": f"[{case.get('category', '')}] {case.get('description', '')}",
    }
    if method in ("POST", "PUT", "PATCH") and "body" in case:
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(case["body"], ensure_ascii=False, indent=2),
            "options": {"raw": {"language": "json"}},
        }

    test_script = compile_test_script(expected_status, case.get("assertions", []))

    example = {
        "id": str(uuid.uuid4()),
        "name": case.get("name", f"case_{case_idx}"),
        "originalRequest": {
            "method": method,
            "header": request["header"],
            "url": {"raw": url_raw, "host": ["{{base_url}}"], "path": segments},
        },
        "status": STATUS_TEXT.get(expected_status, "OK"),
        "code": expected_status,
        "_postman_previewlanguage": "json",
        "header": [{"key": "Content-Type", "value": "application/json"}],
        "cookie": [],
        "body": json.dumps(mock_response, ensure_ascii=False, indent=2),
    }
    if "body" in case:
        example["originalRequest"]["body"] = request["body"]

    return {
        "name": f"{case.get('name', f'case_{case_idx}')} [{case.get('category', '')}]",
        "event": [
            {
                "listen": "test",
                "script": {"exec": [line + "\r" for line in test_script], "type": "text/javascript", "packages": {}, "requests": {}},
            }
        ],
        "request": request,
        "response": [example],
    }


def build_collection(title: str, description: str, endpoints_with_cases: list) -> dict:
    items = []
    for path, method, cases in endpoints_with_cases:
        folder_items = [
            build_request_item(path, method, case, idx)
            for idx, case in enumerate(cases, start=1)
        ]
        items.append({"name": f"{method} {path}", "item": folder_items})

    return {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": title,
            "description": description,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
        "event": [
            {"listen": "prerequest", "script": {"type": "text/javascript", "packages": {}, "exec": [""]}},
            {"listen": "test", "script": {"type": "text/javascript", "packages": {}, "exec": [""]}},
        ],
        "variable": [{"key": "base_url", "value": ""}],
    }


def build_environment(name: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "values": [{"key": "base_url", "value": "", "type": "default", "enabled": True}],
        "color": 300,
        "_postman_variable_scope": "environment",
    }


# ── 설계 문서 ────────────────────────────────────────────────────────

def write_design_doc(out_path: str, spec: dict, endpoints_with_cases: list):
    lines = [f"# {spec.get('info', {}).get('title', 'API')} 테스트 설계 (AI 생성 초안)", ""]
    lines.append(
        "`generate_api_tests.py`가 OpenAPI 명세를 읽고 Groq(llama-3.3-70b)로 생성한 테스트케이스 "
        "초안입니다. LLM은 테스트 의도(카테고리/조건/기대값)까지만 생성하고, 실행되는 Postman test "
        "script(JS)는 파이썬 코드가 결정적으로 컴파일합니다."
    )
    lines.append("")
    total = 0
    for path, method, cases in endpoints_with_cases:
        lines.append(f"## {method} {path}")
        lines.append("")
        lines.append("| # | 카테고리 | 이름 | 기대 상태코드 | 설명 |")
        lines.append("|---|---|---|---|---|")
        for i, c in enumerate(cases, start=1):
            lines.append(
                f"| {i} | {c.get('category', '')} | {c.get('name', '')} | "
                f"{c.get('expected_status', '')} | {c.get('description', '')} |"
            )
            total += 1
        lines.append("")
    lines.append(f"**총 {total}개 테스트케이스 생성됨** (카테고리: {', '.join(CATEGORY_GUIDE.keys())})")
    lines.append("")
    lines.append(
        "## 왜 이렇게 만들었는가\n"
        "- 명세만 넣으면 카테고리별(정상/경계값/상태전이/예외처리) 테스트 초안이 자동으로 나오게 해서, "
        "API 스펙이 바뀔 때마다 테스트를 처음부터 다시 설계하지 않고 재생성 후 검토만 하면 되도록 함\n"
        "- assertion을 LLM이 만든 JS 코드 그대로 실행하지 않고, LLM은 구조화된 의도(JSON)만 만들고 "
        "파이썬이 실제 test script로 컴파일 — LLM이 만든 코드를 곧바로 신뢰하지 않고 사람이 검증 가능한 "
        "중간 표현을 거치게 한 설계\n"
        "- 실제 API가 없으므로 각 케이스의 mock_response를 Postman Mock Server 응답으로 등록해 사용 "
        "(운영 방식은 DELIVERY_TYPE_MOCK_TEST 컬렉션과 동일)"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── 메인 ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spec_path", help="OpenAPI YAML/JSON 파일 경로")
    parser.add_argument("--out-prefix", default=None, help="출력 파일 접두어 (기본: 스펙 title)")
    args = parser.parse_args()

    spec = load_spec(args.spec_path)
    title = spec.get("info", {}).get("title", "API")
    prefix = args.out_prefix or re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").upper()

    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    endpoints = list(iter_endpoints(spec))
    print(f"=== {title}: 엔드포인트 {len(endpoints)}개 발견 ===")

    endpoints_with_cases = []
    for i, (path, method, op) in enumerate(endpoints, start=1):
        print(f"\n[{i}/{len(endpoints)}] {method} {path} — 테스트케이스 생성 중...")
        cases = call_groq_for_cases(groq_client, path, method, op)
        cases = [sanitize_case(c) for c in cases]
        cases = dedupe_path_params(path, cases)
        print(f"  {len(cases)}개 생성됨: " + ", ".join(f"{c.get('category')}" for c in cases))
        endpoints_with_cases.append((path, method, cases))
        if i < len(endpoints):
            time.sleep(5)

    collection = build_collection(
        f"{prefix}_TEST",
        f"{title} — OpenAPI 명세 기반 AI 생성 테스트케이스 (generate_api_tests.py, docs 참고)",
        endpoints_with_cases,
    )
    environment = build_environment(f"{prefix} MOCK ENV")

    collection_path = f"{prefix}_TEST.postman_collection.json"
    env_path = f"{prefix}_MOCK_ENV.postman_environment.json"
    doc_path = os.path.join("docs", f"{args.spec_path.split('/')[-1].rsplit('.', 1)[0]}_test_design.md")

    with open(collection_path, "w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False, indent=2)
    with open(env_path, "w", encoding="utf-8") as f:
        json.dump(environment, f, ensure_ascii=False, indent=2)
    os.makedirs("docs", exist_ok=True)
    write_design_doc(doc_path, spec, endpoints_with_cases)

    total_cases = sum(len(c) for _, _, c in endpoints_with_cases)
    print(f"\n=== 완료: {len(endpoints)}개 엔드포인트 / {total_cases}개 테스트케이스 ===")
    print(f"  컬렉션: {collection_path}")
    print(f"  환경: {env_path}")
    print(f"  설계 문서: {doc_path}")


if __name__ == "__main__":
    main()
