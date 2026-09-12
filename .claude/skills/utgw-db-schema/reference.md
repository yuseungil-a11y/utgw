# UTGW 경영관리 그룹웨어 — DB 스키마 참조 (solweb)

`solweb` MySQL DB의 테이블을 기능 영역별로 정리한 구조 참조입니다. 컬럼 단위 상세와
실제 데이터 현황은 저장소 외부에 별도 보관 중인 데이터 사전 문서를 참고하세요(레포에는
구조/명명 규칙만 남깁니다).

## 테이블 그룹별 요약

### 인사 · 근태
_사원 마스터, 근무형태, 휴가, 시간외근무, 투입인력 등급 관리_

| 테이블 | 용도 |
|---|---|
| `tb_employee` | 사원 마스터 |
| `tb_employee_log` | 사원정보 변경이력 |
| `tb_employee_emotion` | 사원 컨디션 기록 |
| `tb_contract` | 근로계약 이력 |
| `tb_certificate` | 사원 보유 자격증 |
| `tb_technology_grade` | 사원 기술등급 |
| `tb_bank_account` | 급여 입금계좌 |
| `tbattendancelog` | 출퇴근 태깅 로그 |
| `tbattendancerfmng` | 근태 정정신청 처리 |
| `tbworkingstatus` | 사원별 근무형태 설정값 |
| `tbworkshapelog` | 근무형태 변경 승인이력 |
| `tb_tm_else_wrkst` | 시간외근무 실적 |
| `tb_wrkst_rcrd_info` | 일별 근태기록 |
| `tb_wrkst_schdul_info` | 근무 예정 스케줄 |
| `tb_wrkst_diary_info` | 프로젝트별 업무일지(투입시간 원천 테이블) |
| `tb_vctn_info` | 연차 발생·사용 현황 |
| `tb_vctn_day_info` | 휴가 사용 일자별 상세 |
| `tb_holiday` | 공휴일 정보 |
| `tb_extms` | 프로젝트 참여인력 등록 마스터 |
| `tb_extms_empl` | 사원별 외부/SW 기술등급 구분값 |
| `tb_extms_month` | 월별 투입률(%) 입력값 |

### 조직 · 권한 · 메뉴
_부서 구조, 로그인 권한, 화면/메뉴 접근 제어_

| 테이블 | 용도 |
|---|---|
| `tb_organization` | 조직(부서) 정보 |
| `tb_part` | 파트(조직 하위단위) |
| `tb_branch` | 지사 정보 |
| `tb_company` | 회사 기본정보 |
| `tb_hq_intr` | 본부 소개 콘텐츠 |
| `tb_auth` | 권한(역할) 정의 |
| `tb_doc_access` | 권한별 전자결재 문서 접근 설정 |
| `tb_menu` | 좌측 메뉴 트리 구조 |
| `tb_menu_access` | 권한별 메뉴 CRUD 접근 설정 |
| `tbauthority` | 사원-권한 매핑 |

### 거래처
| 테이블 | 용도 |
|---|---|
| `tb_account` | 거래처(고객사/협력사) 기본정보 |
| `tb_account_manager` | 거래처 담당자 연락처 |

### 프로젝트 · 영업/제안
_수주 전 단계_

| 테이블 | 용도 |
|---|---|
| `table18` | 영업단계 워크플로우 진행상태 |
| `tb_prj_pre_sales` | 사전영업(프리세일즈) |
| `tb_prj_prpsl` | 제안 진행 일정 |
| `tb_prj_prpsl_attch_file` | 제안 관련 첨부파일 매핑 |

### 프로젝트 · 기본정보
_수주 이후 프로젝트 마스터와 계약 · 투입인력 배정_

| 테이블 | 용도 |
|---|---|
| `tb_prj_info` | 프로젝트 마스터(코드/이름/기간/조직) |
| `tb_prj_stp` | 프로젝트 진행단계 변경이력 |
| `tb_prj_exc` | 착수·중간·종료보고 일정 |
| `tb_prj_exc_attch_file` | 수행단계 첨부파일 매핑 |
| `tb_prj_inp_mp` | 프로젝트 투입인력 배정(역할·기간) |
| `tb_prj_contrt` | 프로젝트 계약 기본정보 |
| `tb_prj_contrt_rcrd` | 계약 상세(실행예산 승인요청과 연결) |

### 실행예산
_원가 배분 승인 프로세스_

| 테이블 | 용도 |
|---|---|
| `tb_prj_exec_bgt` | 프로젝트별 승인된 실행예산 버전 이력 — 재승인은 증액이 아닌 전체 재작성 방식이라 최신 버전만 유효 |
| `tb_request_exec_bgt` | 실행예산 승인요청 총액 |
| `tb_request_exec_bgt_expens` | 실행예산 경비 세부내역 |
| `tb_request_exec_bgt_lbcst` | 실행예산 노무비 세부내역 |
| `tb_request_exec_bgt_prchss` | 실행예산 외주(매입) 내역 |
| `tb_exec_bgt_rate` | 실행예산 계산용 기준 비율 |
| `tb_labor_cost` | 직급별·연도별 노무비 단가표 — solweb 원본 테이블이 아니라 이 앱이 직접 생성·시딩 |

### 매출 · 매입
| 테이블 | 용도 |
|---|---|
| `tb_prj_sales_prchss` | 프로젝트 매출/매입 청구 현황 |
| `tb_prj_sales_prchss_mdfd_rcrd` | 매출/매입 상태변경 이력 |
| `tb_request_sales_prchss` | 매출/매입 등록요청 |

### 전자결재 · 요청
_모든 결재문서가 공통 헤더(`tb_request`)를 거치고 문서종류별 상세 테이블로 갈라짐_

| 테이블 | 용도 |
|---|---|
| `tb_request` | 전자결재 요청 공통 헤더 |
| `tb_request_approved` | 결재선별 승인/반려 처리 현황 |
| `tb_request_drrq` | 기안서 본문 |
| `tb_request_drrq_form` | 기안서 양식 템플릿 |
| `tb_mng_approved_process` | 문서종류별 결재라인 설정 |
| `tb_mng_document` | 전자결재 문서종류 마스터 |
| `tb_mng_document2` | 문서종류 마스터 예비 테이블 |
| `tb_request_vctn` | 휴가 신청 |
| `tb_request_expenses` | 경비 지출결의 신청 |
| `tb_request_exps_decsn` | 경비 정산 확정 처리 |
| `tb_request_businesstrip_order` | 출장명령 신청 |
| `tb_request_flextime` | 시차출퇴근 신청 |
| `tb_request_work_home` | 재택근무 신청 |
| `tb_request_wrkst_mdat` | 근태 정정 신청 |
| `tb_request_cowork_project` | 타부서 협업 지원요청 |
| `tb_request_cwk_inp_mp_info` | 협업요청 투입인력 배정 |
| `tb_request_cwk_inp_role` | 협업요청 역할별 인건비 정보 |
| `tb_request_input_project` | 프로젝트 투입 신청 |
| `tb_request_tm_else_wrkst` | 시간외근무 신청 |

### 게시판 · 메시지 · 알림
| 테이블 | 용도 |
|---|---|
| `tb_board_category` | 게시판 종류 |
| `tb_board_post` | 게시글 |
| `tb_board_comment` | 게시글 댓글 |
| `tb_message_send` | 발신 쪽지 |
| `tb_message_receive` | 수신 쪽지 열람현황 |
| `tbnotificationsinfo` | 시스템 알림 발생이력 |

### 공용자원 예약
| 테이블 | 용도 |
|---|---|
| `tb_meetroom_info` | 회의실 정보 |
| `tb_meetroom_resv` | 회의실 예약 |
| `tb_car_info` | 법인차량 정보 |
| `tb_car_resv` | 법인차량 예약 |

### 공통코드 · 첨부파일 · 기타
_전 화면이 공유하는 코드 테이블과 파일 저장소_

| 테이블 | 용도 |
|---|---|
| `tb_main_category` | 공통 대분류 코드 |
| `tb_sub_category` | 공통 소분류 코드(드롭다운 값 원천) |
| `tb_attach_file` | 첨부파일 개별 정보 |
| `tb_attach_file_group` | 첨부파일 묶음 단위 |
| `tb_solution` | 조직별 보유 솔루션 소개자료 |

### 외부 연동 (그룹웨어 무관)
_이 경영관리 프로그램이 아니라 다른 사내 시스템이 같은 DB(solweb)를 함께 쓰면서 만든 테이블_

| 테이블 | 용도 |
|---|---|
| `tb_api_key_manager` | 별도 시스템의 API 키 관리 테이블. 이 그룹웨어 코드에서는 참조하지 않음(민감정보 포함이라 상세 미기재) |
