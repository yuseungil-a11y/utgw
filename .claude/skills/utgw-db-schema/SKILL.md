---
name: utgw-db-schema
description: UTGW 경영관리 그룹웨어(solweb MySQL DB)의 테이블 구조·용도와 이 코드베이스 특유의 데이터 함정을 정리한 참조 지식. 새 화면/쿼리를 만들거나 기존 기능이 어느 테이블을 쓰는지 확인할 때, DB 관련 버그를 조사할 때 사용.
---

# UTGW 경영관리 그룹웨어 — DB 스키마 참조

`solweb` MySQL DB의 테이블을 기능 영역별로 정리한 참조 지식입니다. 접속 정보(호스트/계정)는
`config.ini`에서 관리하며 이 문서에는 포함하지 않습니다.
전체 목록은 [reference.md](reference.md)에 표로 정리되어 있고, 컬럼 수준 상세와 실제 데이터 현황은
저장소 외부에 별도 보관 중인 데이터 사전 문서를 참고하세요.

## 사용 시점

- 새 화면/쿼리에 필요한 데이터가 어느 테이블에 있는지 찾을 때 → [reference.md](reference.md)에서 기능 영역(그룹)별로 훑어본다.
- 기존 기능이 참조하는 테이블을 파악할 때 → 테이블명으로 `app/queries/*.py`를 grep하기 전에 먼저 여기서 용도를 확인한다.
- DB 관련 버그를 조사할 때 → 아래 "알려진 함정" 절부터 확인한다. 실제로 발생했던 이중집계·집계 오류가 여기 정리되어 있다.
- 새 테이블/컬럼을 추가하기 전 → 기존 명명 규칙(`tb_` 접두어, 대문자 컬럼명)과 유사 테이블 유무를 확인한다.

## 코드베이스 전반의 규칙

- 테이블명은 거의 전부 `tb_` 접두어 + snake_case (예외: `table18`, `tbattendancelog` 등 레거시 6개 테이블).
- 컬럼명은 DB 자체가 대문자 스네이크 표기(예: `EXEC_BGT_CD`, `APPD_DTTM`). Python 쪽 조회 코드(`app/queries/*.py`)도 이를 그대로 딕셔너리 키로 사용한다.
- 공통 대/소분류 코드는 `tb_main_category`/`tb_sub_category`에 몰려 있다 — 근태·경비·프로젝트 등 거의 모든 드롭다운의 원천. 새 코드값이 필요하면 새 테이블을 만들기 전에 이 두 테이블에 이미 있는지 먼저 확인한다.
- 모든 전자결재 문서는 공통 헤더 `tb_request`를 거치고, 문서종류별 상세 테이블(`tb_request_vctn`, `tb_request_expenses` 등)로 갈라진다. 결재선 진행상황은 `tb_request_approved`(요청 1건당 결재자 수만큼 행 생성)에서 확인한다.
- DB 접근은 `app/db.py`의 `fetch_all`/`fetch_one`/`execute`/`execute_many`만 사용하고, `ReadOnlyQueryError`로 SELECT 외 쿼리를 막고 있다.

## 알려진 함정 (엔지니어링 유의사항)

- `tb_prj_exec_bgt`(실행예산)의 재승인은 증액이 아니라 전체 재작성 방식이다. 버전이 여러 건 쌓이므로 최신 승인 건(`APPD_DTTM` 기준)만 사용해야 하며, 모두 합산하면 이중집계가 된다(`app/queries/project_cost.py`의 `_build_req_to_prj_map()` 참고).
- `tb_labor_cost`는 solweb 원본 테이블이 아니라 이 앱이 직접 생성·시딩한다(`app/queries/labor_cost.py`). 직급 코드는 새로 만들지 않고 기존 `tb_sub_category`를 참조한다.
- `tb_api_key_manager`는 이 그룹웨어와 무관한 별도 시스템의 테이블이다. 코드에서 참조하지 않으며, 민감정보를 포함하므로 조회 결과를 문서·로그에 남기지 않는다.
- M/M(맨먼스) 환산은 160시간/월 기준, 소수점 1자리로 반올림한다(`app/ui/project_headcount_dialog.py`의 `_to_mm()`).
- `tb_wrkst_diary_info`는 프로젝트별·사람별 투입시간의 원천 테이블이다(`app/queries/project_headcount.py`). 프로젝트 기준 화면은 인원이 2명 이상이면 세부 행을 추가하므로(그룹 구조) 헤더 정렬을 켜지 않는다.

## 전체 테이블 목록

[reference.md](reference.md)에 12개 기능 영역(인사·근태, 조직·권한·메뉴, 거래처, 프로젝트·영업/제안,
프로젝트·기본정보, 실행예산, 매출·매입, 전자결재·요청, 게시판·메시지·알림, 공용자원 예약,
공통코드·첨부파일·기타, 외부 연동)으로 나눠 테이블명·용도를 정리해 두었습니다.
