# 0.4.1 추가 조사

[OPDS 1.2 규격](https://specs.opds.io/opds-1.2.html)은 acquisition 링크를 가진 책 목록을 acquisition feed로 구분한다. 현재 Readest/foliate-js의 getFeed도 같은 링크를 기준으로 publication을 구분한다. 이전 플러그인의 책 목록에는 표지와 하위 목록 링크만 있어 navigation 카드로 표시되었다.

Readest FeedView의 publications 분기는 PublicationCard를 그리드로 렌더링하고, PublicationCard는 표지 아래 제목과 저자를 표시한다. 이번에는 앱 코드 수정 없이 플러그인이 모든 회차 acquisition 링크를 순서대로 포함하도록 변경했다. get_db_gateway('audiobook').fetch_all로 페이지 ID를 매개변수화한 배치 쿼리 1회를 수행한다. 실제 쿼리와 parser로 검증했으며 새 BookOasis API를 추측해 추가하지 않았다.

아래는 이전 버전의 기반 API/정렬 조사 기록이다.

# 0.4.0 추가 확인

audiobooks의 title, created_at, updated_at 필드를 공식 스키마에서 확인했다. 정렬용 DB API를 새로 추측하지 않고 기존 get_db_gateway('audiobook').fetch_all을 사용한다. Readest의 실제 OPDS parser와 메뉴는 표준 facetGroup/activeFacet을 지원한다.

아래는 기존 플러그인 기반 API 조사 기록이다.

# 공식 소스 조사 기록

조사 기준일: 2026-10-23. 공개 저장소를 고정 커밋으로 조사하고 실제 운영 이미지의 주요 파일과 대조했다. 소스 계약과 실행 검증 결과는 구분해 기록한다.

## 조사 대상과 버전의 경계

- 공식 저장소: [leeyj/BookOasis_stable](https://github.com/leeyj/BookOasis_stable)
- 조사에 고정한 커밋: [`f4f80943bc46e8b673674b88bc40fc16bfafbd98`](https://github.com/leeyj/BookOasis_stable/tree/f4f80943bc46e8b673674b88bc40fc16bfafbd98)
- 공식 가이드: [docs/guide_plugins.md](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/docs/guide_plugins.md)
- 공식 샘플: [sample_plugins/metadata/rss_epub_news](https://github.com/leeyj/BookOasis_stable/tree/f4f80943bc46e8b673674b88bc40fc16bfafbd98/sample_plugins/metadata/rss_epub_news)

사용자가 확인한 실제 환경은 Ubuntu 24.04.4 LTS, 컨테이너 `bookoasis`, 이미지 `ghcr.io/leeyj/bookoasis:stable`, 대시보드 3.0.2, 기존 공개 포트 5930이다. 이미지의 `stable` 태그와 대시보드 버전만으로 실행 중인 이미지의 정확한 Git 커밋까지 확인되지는 않는다. 따라서 이 보고서의 줄 번호와 구현 설명은 위 커밋을 기준으로 한다. 사용자가 운영 설치 코드에서 확인한 `get_db_gateway`, 백그라운드 서비스 시작 후크 및 `'general'` 인수는 별도 확인 사실로 반영했다.

## 검증한 플러그인 계약

| 항목 | 소스로 확인한 동작 | 구현에 적용할 사항 |
|---|---|---|
| 디렉터리 | 가이드는 `plugins/metadata/<id>/` 폴더 구조를 권장한다. [가이드 61행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/docs/guide_plugins.md#L61) | 폴더명·주 파일명·ID를 사용자가 지정한 `audiobook_opds`로 통일한다. |
| 베이스 클래스 | 공식 import는 `plugins.metadata.base.BaseMetadataProvider`; 실제 구현은 `plugin_framework/metadata_base.py`에 있다. [가이드 245행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/docs/guide_plugins.md#L245) | 코어 파일을 복사하거나 수정하지 않고 상속한다. |
| 필수 메서드 | `search`와 `apply`가 abstractmethod다. [베이스 274행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/plugin_framework/metadata_base.py#L274) | OPDS 서비스도 두 메서드를 구현한다. 검색 비노출은 `is_searchable = False`로 표현한다. |
| 비검색 샘플 | RSS 샘플은 `is_searchable = False`, `search`에서 빈 목록, `apply`에서 실패 여부와 설명을 반환한다. [샘플 544행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/sample_plugins/metadata/rss_epub_news/rss_epub_news.py#L544) | 서비스 플러그인의 비검색 동작에 참고한다. |
| 로더 | 패키지, 패키지 내 같은 이름의 모듈, `provider` 모듈 순으로 import를 시도하고 베이스의 하위 클래스를 찾는다. [factory 287행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/services/metadata_factory.py#L287) | `audiobook_opds/audiobook_opds.py` 구조가 실제 로딩 경로에 포함된다. |
| DB 게이트웨이 | `get_db_gateway(db_type)`가 DB 타입별 gateway 인스턴스를 캐시한다. [베이스 81행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/plugin_framework/metadata_base.py#L81) | 오디오북 데이터 조회에는 `get_db_gateway('audiobook')`를 사용한다. |
| 설정 헬퍼 | `get_plugin_config`는 해당 gateway의 `get_plugin_config(self.id)`를 호출한다. [베이스 93행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/plugin_framework/metadata_base.py#L93) | 플러그인 설정은 `get_plugin_config('general', default={})`로 읽는다. |
| 시작 인수 | 활성 플러그인 클래스를 새로 인스턴스화한 뒤 `start_background_service('general')`을 호출한다. [factory 726행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/services/metadata_factory.py#L726) | 후크의 `db_type`을 오디오북 데이터 DB로 오인하지 않는다. |
| 후크의 반환 | 초기화나 블로킹 루프는 자체 스레드로 넘기고 후크가 즉시 반환해야 한다. [베이스 268행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/plugin_framework/metadata_base.py#L268) | 별도 HTTP 서비스를 데몬 스레드에서 실행한다. |

## 설정 저장과 UI

- 설정 키는 `PLUGIN_CONFIG_<id>`이고 값은 JSON 문자열이다. gateway가 이를 dict로 읽으며 JSON 파싱 실패·비객체 값에는 default를 반환한다. [services/plugin_db_gateway.py 54행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/services/plugin_db_gateway.py#L54)
- factory는 플러그인 목록의 설정과 활성 여부를 **general DB**에서 읽는다. [services/metadata_factory.py 616행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/services/metadata_factory.py#L616)
- 저장 API는 요청의 `type` 값을 사용한다. 이 플러그인의 설정은 일반 도서 세션(`general`)에서 저장해야 목록과 시작 후크의 설정 조회와 일치한다. [api/routes/plugin_routes.py 203행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/api/routes/plugin_routes.py#L203)
- `settings.html`이 있으면 `config_schema` 자동 폼 대신 커스텀 마크업을 사용한다. [static/js/settings/plugins.js 27행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/static/js/settings/plugins.js#L27)
- 저장할 때 수집하는 요소는 `input, select`다. checkbox는 bool, 다른 값은 trim한 문자열이다. `textarea`는 수집되지 않는다. [static/js/settings/plugins.js 407행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/static/js/settings/plugins.js#L407)
- 설정·활성 여부 저장은 DB 값을 저장할 뿐 서비스 시작·정지·재시작 후크를 호출하지 않는다. [services/plugin_service.py 312행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/services/plugin_service.py#L312)

`audiobook_opds`의 서비스 설정은 general DB에 두고 서비스 supervisor가 주기적으로 재조회한다. 부팅 때 코어 플러그인 토글이 꺼져 있었다면 supervisor 자체가 생성되지 않으므로, 토글을 켠 후 컨테이너 재시작이 필요하다.

## 가이드와 실제 코드의 불일치

가이드는 gateway의 주요 메서드 중 `transaction()`을 열거한다. [가이드 1226행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/docs/guide_plugins.md#L1226) 그러나 [실제 PluginDatabaseGateway 전체](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/services/plugin_db_gateway.py)에는 그 메서드가 없다. 이 메서드가 존재한다고 가정해 사용하지 않는다.

실제 확인한 메서드는 `fetch_one`, `fetch_all`, `execute`, `execute_many`, `get_setting`, `set_setting`, `get_plugin_config`, `set_plugin_config`다. `get_setting`은 원시 값이 아니라 `{'value': 값}` 또는 default를 반환한다. [gateway 45행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/services/plugin_db_gateway.py#L45)

## 워커와 별도 포트의 수명주기

- 앱 부팅 중 `core.py`가 서비스 시작 후크를 호출한다. [core.py 596행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/core.py#L596)
- 현재 Docker 기본 명령은 `gunicorn --workers 1 --threads 12`, 기존 포트 5930, timeout 300초, graceful timeout 15초다. [Dockerfile 78행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/Dockerfile#L78)
- RSS 샘플 문서는 여러 워커에서도 후크가 호출될 수 있다고 설명하고 날짜별 `O_EXCL` lock으로 일일 작업을 선점한다. [샘플 README 47행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/sample_plugins/metadata/rss_epub_news/README.md#L47) 현재 Docker 기본 명령의 워커 수는 1개지만, 사용자가 변경할 수 있으므로 별도 listener의 중복 시작을 방지해야 한다.
- 일일 작업의 lock 파일을 장기 listener의 소유권 방식으로 그대로 사용하면 비정상 종료 뒤 잔존할 수 있다. listener의 독점 bind 및 재시도, 프로세스 내부 중복 시작 방지, 종료 시 정리 방식이 필요하다.
- `gunicorn.conf.py`는 워커 종료 시 `atexit._run_exitfuncs()`를 실행한 뒤 `os._exit(0)` 한다. 정리 작업 자체가 멈추는 경우를 위한 20초 watchdog도 있다. [gunicorn.conf.py 14행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/gunicorn.conf.py#L14)
- 플러그인 Python 코드의 외부 프로세스 실행은 기본 정적 검사에서 차단된다. 이 서비스는 자체 Python 스레드를 사용한다. [가이드 91행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/docs/guide_plugins.md#L91)

## OPDS 및 오디오 전달 방식

1. [OPDS Catalog 1.2 공식 규격](https://specs.opds.io/opds-1.2)은 Atom 기반 navigation/acquisition feed와 acquisition 링크, 표지·썸네일 링크를 정의한다. feed 링크 type에는 `profile=opds-catalog`와 `kind=acquisition` 또는 `kind=navigation`을 사용한다.
2. 인증이 필요한 완전한 파일에는 일반 `http://opds-spec.org/acquisition` 관계가 맞는다. `open-access`는 등록 등 선행 요구 없이 콘텐츠를 받을 수 있다는 의미이므로 이 인증 서비스의 관계로 사용하지 않는다.
3. 같은 규격은 Basic 인증과 TLS 연결을 지원하도록 정하고, 인증 실패 응답에 적절한 401/403을 사용하도록 안내한다. 외부 접속에서는 신뢰할 수 있는 TLS 종단을 구성한다.
4. [OPDS-PSE 1.2 원저자 규격](https://anansi-project.github.io/docs/opds-pse/specs/v1.2)은 **만화의 페이지 이미지 스트리밍** 확장이다. stream 링크는 이미지 형식, 페이지 수, `{pageNumber}`를 요구한다. MP3/M4B 오디오에 이 관계를 붙이지 않는다.
5. 각 MP3/M4A/M4B 트랙은 OPDS acquisition 링크의 `audio/mpeg` / `audio/mp4` 리소스로 전달하고, 재생 중 위치 탐색은 HTTP byte Range로 처리한다. Range의 의미와 206/416 응답은 [RFC 9110, Range Requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-range-requests)를 따른다.

Android 앱의 오디오 형식 인식, 인증 전달 및 재생 위치 저장 동작은 앱 구현에 따라 다르다. 프로토콜 검증과 실제 앱에서의 목록·재생·구간 이동 검증은 별개로 기록해야 한다. OPDS 1.2만으로 앱 간 재생 위치 동기화 계약이 생기지는 않는다.

## 인증·권한·파일 조회의 실제 근거

| 항목 | 공식 소스와 적용 |
|---|---|
| 인증 계정 | [api/opds_common/auth.py 9행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/api/opds_common/auth.py#L9): `general` 사용자 계정과 `check_password_hash`로 인증한다. |
| 계정 필드 | [repositories/sqlite/user_repository.py 13행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/repositories/sqlite/user_repository.py#L13): 존재하는 사용자·암호·role·초기암호·오디오북·다운로드 필드를 조회한다. `active`나 `status` 같은 미확인 필드는 만들지 않았다. |
| 초기 암호 | [api/auth.py 110행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/api/auth.py#L110): 초기 암호 상태의 API 차단을 플러그인에도 적용한다. |
| 오디오북 권한 | [api/auth.py 155행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/api/auth.py#L155): 관리자 또는 `has_audiobook_access == 1`. |
| 다운로드 권한 | [api/auth.py 173행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/api/auth.py#L173): 관리자 또는 `has_download_access == 1`. |
| 카테고리 권한 | [repositories/sqlite/category_repository.py 659행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/repositories/sqlite/category_repository.py#L659): `user_category_permissions`의 `user_id`, `library_id`, `has_access=1` 조건. 공식 helper는 DB 오류에서 허용을 반환하므로 그대로 재사용하지 않고 audiobook gateway 쿼리에 같은 조건을 넣어 오류 시 503으로 차단한다. |
| 삭제 상태 | [카테고리 213행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/repositories/sqlite/category_repository.py#L213), [오디오북 repository 32행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/repositories/sqlite/audiobook_repository.py#L32): `pending_delete`와 `is_deleted`를 제외한다. |
| 오디오북 스키마 | [services/db_migration_service.py 316행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/services/db_migration_service.py#L316): `audiobooks`와 `audiobook_tracks`의 실제 컬럼을 사용한다. `total_tracks` 대신 실제 트랙 행을 조회한다. 트랙 순서는 `track_number`, ID 순이다. |
| 표지 소스 | [utils/cover_helper.py 52행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/utils/cover_helper.py#L52): 로컬 이미지, metadata.json, 내장 표지의 기존 처리 경로를 확인했다. 로컬 경로는 라이브러리 경계 안에서만 읽는다. |
| 외부 표지 | [utils/cover_helper.py 187행](https://github.com/leeyj/BookOasis_stable/blob/f4f80943bc46e8b673674b88bc40fc16bfafbd98/utils/cover_helper.py#L187): `get_or_cache_external_image_webp`는 공개 URL·리다이렉트 검증과 기본 2MiB 응답 제한을 제공한다. |
| 상세 OPDS Entry | [OPDS 1.2 §5.1.2](https://specs.opds.io/opds-1.2#512-partial-and-complete-catalog-entries): `alternate`는 `application/atom+xml;type=entry;profile=opds-catalog` 타입이며 상세 응답은 standalone `atom:entry`로 제공한다. |

각 요청에서 계정을 general DB로 인증하고, 그 ID로 audiobook DB의 카테고리 권한을 확인한다. 오디오북 DB에 같은 이름의 다른 계정이 있어도 인증 원본으로 사용하지 않는다. 경로는 숫자 ID에서 DB로 조회하며 요청의 파일 경로를 받아 열지 않는다.

## 조사 기록의 범위

이 문서는 공식 계약·설정·시작 수명주기 및 전송 규격의 근거를 기록한다. 인증·라이브러리 접근권한·오디오북 저장 스키마에 관한 구현 근거와 실행 테스트 결과는 해당 구현 및 검증 기록에서 별도로 확인한다. 운영 설치와 실행 결과는 VALIDATION 문서에 기록한다. Android 실기 검증은 아직 수행하지 않았다.

## 0.2.0 다중 트랙 확장과 운영 대조

실제 `api/routes/audiobook_routes.py`의 331~332행에서 M4A/M4B MIME가 `audio/mp4`임을 확인했다. 트랙 스키마의 `id`, `audiobook_id`, `track_number`, `title`, `artist`, `file_path`, `filename`, `duration`, `file_size`를 사용한다. 임의의 파일 경로를 HTTP 인수로 받지 않는다. 책 목록은 navigation feed, 책의 트랙 목록은 acquisition feed다. 각 트랙의 acquisition 링크를 별도로 제공한다.

운영 컨테이너의 VERSION·베이스·factory·gateway·인증·오디오북 route·cover helper·core·Dockerfile 9개 파일을 해당 공식 Git blob의 SHA256과 대조해 일치를 확인했다. 사용 이미지 ID는 `sha256:adc044dbfd67f177d13e4241e0ff2e0d6fbd110680164992c3fdb59d9febd90b`다. 실행 결과는 VALIDATION 문서를 따른다.

코어 `MetadataFactory.get_available_providers`는 `PLUGIN_ENABLED_<id>`의 정확한 문자열 `'1'`을 활성화로 취급한다. `'true'`를 쓰지 않는다. 초기 설치 시 이 차이로 listener가 시작되지 않았던 시도는 자동으로 이전 설정으로 되돌렸으며 최종 설정은 `'1'`이다.

## 0.3.0 카테고리 우선 탐색

실제 `libraries`의 `id`, `name`, `sort_order`, `pending_delete`와 `user_category_permissions`를 사용한다. `repositories/sqlite/category_repository.py`의 기존 카테고리 순서는 sort_order/name 순이며 새 OPDS도 이를 따른다. `library_groups` 구조도 확인했으나 현재 오디오북 14개 카테고리는 같은 오디오북 그룹에 있어 불필요한 그룹 단계를 추가하지 않았다.

첫 `/opds` 응답에 각 카테고리를 atom:entry + subsection 링크로 넣는다. 이전처럼 전체 책을 첫 응답에 나열하거나 feed-level 링크에만 카테고리를 숨기지 않는다. 카테고리의 권수는 삭제되지 않고 지원 확장자 트랙이 있는 책 수다. 권한 없는 카테고리는 이름·권수가 노출되지 않으며 직접 주소와 검색 설명 주소도 404다. 데이터 조회는 계속 audiobook gateway로만 수행한다.

## 0.3.1 Readest 호환 계약

공식 Readest v0.12.10의 `PublicationView.tsx`는 acquisition 관계 오디오 링크를 전부 골라 문서 순서대로 하나의 재생 목록을 만든다. 다중 트랙 상세에 subsection만 있던 기존 응답에서는 오디오 링크가 0개이므로 No downloadable format available을 표시한다.

완전한 책 상세에 모든 지원 트랙을 track_number/id 순으로 넣고 파일당 acquisition 한 개만 제공한다. 같은 오디오를 가리키는 stream/download 둘을 acquisition으로 넣으면 두 트랙으로 재생하므로 별도 다운로드 링크는 Atom related 관계로 제공한다. 다운로드 URL의 권한 검사는 유지한다. 링크 title에 트랙명을 쓰며 XML 제어문자도 정리한다. 단일 책 상세의 기존 stream 주소와 트랙별 주소는 유지한다.

검증에는 실제 Readest의 상세 컴포넌트·오디오 포맷 판별·트랙 선택 코드를 사용했다. 부수 UI·플랫폼 의존성만 별도 stub으로 대체해 React server render로 재현했다. 휴대폰 UI나 오디오 엔진 실행을 의미하지 않는다. 원본 소스와 Git blob 해시·라이선스·재현 방법은 verification/readest에 있다.
