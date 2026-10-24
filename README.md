# BookOasis Audiobook OPDS

BookOasis의 오디오북을 OPDS로 탐색하고, Android에서 회차를 골라 재생하기 위한 비공식 프로젝트입니다.

- **플러그인 `audiobook_opds` 0.4.1:** 카테고리, 표지 그리드, 제목/날짜 정렬, 인증, MP3·M4A·M4B 스트리밍과 다운로드
- **Readest BookOasis b3:** Readest 0.12.16을 수정한 별도 Android 앱. 회차 목록에서 선택한 파일부터 준비하고 재생
- BookOasis와 Readest 원본 프로젝트가 배포하는 공식 플러그인·공식 앱은 아닙니다.

## 다운로드

**[첫 배포 릴리스](https://github.com/hejerd/bookoasis-audiobook-opds/releases/tag/v0.4.1-b3)**

| 파일 | 용도 |
| --- | --- |
| [audiobook_opds-0.4.1.zip](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.1-b3/audiobook_opds-0.4.1.zip) | BookOasis 서버 플러그인, 소스, 문서, 샘플 테스트 |
| [Readest-BookOasis-0.12.16-b3-arm64.apk](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.1-b3/Readest-BookOasis-0.12.16-b3-arm64.apk) | Android 8 이상 · arm64-v8a 설치 파일 |
| [Readest-BookOasis-0.12.16-b3-source.zip](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.1-b3/Readest-BookOasis-0.12.16-b3-source.zip) | 해당 APK의 전체 수정 소스, 고정 하위 모듈, 빌드 문서 |
| [SHA256SUMS.txt](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.1-b3/SHA256SUMS.txt) | 다운로드 파일 SHA256 |

GitHub가 자동 생성하는 저장소 소스 ZIP은 이 저장소의 플러그인과 문서를 담습니다. **Readest 앱의 전체 대응 소스는 별도 첨부한 `Readest-BookOasis-0.12.16-b3-source.zip`입니다.**

## 서버 설치

검증 기준: BookOasis dashboard 3.0.2, Ubuntu 24.04, Docker. 공식 소스의 `BaseMetadataProvider` 시작 후크(`general`)와 `get_db_gateway('audiobook')`를 사용합니다. 코어·DB 스키마를 수정하지 않습니다.

1. 기존 BookOasis 설정·DB·플러그인을 백업합니다.
2. BookOasis 컨테이너를 정지하고 ZIP의 **`plugins/metadata/audiobook_opds/` 폴더만** 기존 플러그인 마운트의 같은 위치에 배치합니다.
3. Docker 포트 매핑에 `5931:5931`을 추가합니다. 이미 있으면 유지합니다. 새 매핑을 추가할 때는 기존 볼륨·환경 변수를 유지해 컨테이너를 재생성합니다.
4. BookOasis를 시작하고 관리자 플러그인 설정에서 **오디오북 OPDS**를 활성화합니다. OPDS 서비스 사용도 켭니다.
5. 기본값은 수신 주소 `0.0.0.0`, 포트 `5931`, 페이지 크기 `30`입니다. 기본 URL은 비워두면 요청 주소를 사용합니다. 프록시 URL을 입력할 때 끝에 `/opds`를 붙이지 않습니다.
6. 앱에 `http://서버주소:5931/opds`와 기존 BookOasis 사용자명·비밀번호를 등록합니다. 외부 접속은 HTTPS 프록시 구성을 사용합니다.

[자세한 설치·설정·롤백](docs/INSTALL.ko.md)

## 탐색과 재생

카탈로그 첫 화면에서 카테고리를 고르면 **표지와 아래 제목**이 그리드로 표시됩니다. 기존 카탈로그 화면은 닫고 다시 열어 새 목록을 받습니다.

- 정렬: 제목 가나다순/역순, 최신/오래된 추가순, 최근 수정순. 작은 화면은 상단 필터 메뉴, 큰 화면은 옆 패널에 표시될 수 있습니다.
- 검색: 카테고리를 선택한 뒤 검색하면 그 카테고리 안에서 찾습니다.
- b3에서 여러 회차의 책을 열면 회차 목록이 먼저 표시됩니다. 중간 회차를 바로 선택할 수 있고 재생 중 **회차 목록** 버튼으로 다시 선택할 수 있습니다.
- 선택한 파일의 길이만 준비합니다. 파일을 하나로 병합하지 않습니다. 재생 시간·탐색 막대는 현재 회차 기준이고, 회차가 끝나면 다음 회차로 이동합니다.
- 마지막 회차와 파일 안의 재생 위치를 저장합니다. 앱과 BookOasis 사이의 위치 동기화는 제공하지 않습니다.

## 인증과 권한

기존 BookOasis 계정의 오디오북 접근·라이브러리 권한과 다운로드 권한을 적용합니다. 기본 암호 상태의 계정은 먼저 BookOasis에서 암호를 변경해야 합니다. 원본 미디어 경로는 허용된 라이브러리/책 폴더 내부인지 검사합니다. 미디어 누락이나 잘못된 기존 경로는 이 플러그인으로 복구되지 않습니다.

## 검증 범위

| 대상 | 실제 수행 결과 |
| --- | --- |
| 플러그인 0.4.1 | 임시 DB·짧은 생성 샘플을 사용한 최종 172개 검사 통과. 초기 171개 통과 + 변경된 피드 계약 검사 1개 수정 후 재실행 통과 |
| 실제 서버 데이터 | 읽기 전용 검사로 450권의 목록/상세 회차 일치, 정렬 75개, 표지 3개, 음원 2개의 HEAD 200·Range 206 확인 |
| Readest b3 | 관련 291개 회귀 테스트, TypeScript, 전체 Biome lint, 프런트엔드·Android 빌드와 APK 서명/정렬 검사 통과 |
| 한계 | b3 Android 실기 소리·백그라운드·초기 대기 시간은 이번 빌드에서 확인하지 못함. Readest 전체 원본 테스트는 범위 밖 실패가 발생해 완료하지 못함. MariaDB 실기 검증 없음 |

[플러그인 검증](docs/VALIDATION.ko.md) · [앱 설치](app/INSTALL.ko.md) · [앱 검증](app/VALIDATION.ko.md) · [앱 빌드](app/BUILD-b3.ko.md)

## 개발과 소스

플러그인 코드는 `plugins/metadata/audiobook_opds/`, 샘플 검사는 `tests/`에 있습니다. 공식 BookOasis 소스 커밋 `f4f80943bc46e8b673674b88bc40fc16bfafbd98`을 기준으로 실제 API를 확인했습니다.

```bash
python -m pytest tests --bookoasis-source /path/to/BookOasis_stable -q
```

테스트 의존성은 Flask, Werkzeug, Pillow, requests, python-dotenv, mutagen, pytest, imageio-ffmpeg 및 BookOasis 실행 의존성입니다. 샘플은 직접 생성한 2초 사인파이며 사용자 오디오북은 포함하지 않습니다.

앱 ID는 `com.bilingify.readest.bookoasis`, 버전은 `0.12.16+bookoasis.3` / Android versionCode `12018`입니다. 기존 BookOasis b1/b2와 동일 서명으로 업데이트할 수 있고 공식 Readest와 별도 설치됩니다. 원본 Readest 커밋은 `27694ba28b590cfb6c4c88092b73d31ed1338de9`입니다. 빌드 문서와 하위 모듈 소스는 앱 소스 ZIP에 포함합니다.

## 원본 프로젝트와 라이선스

- [BookOasis_stable](https://github.com/leeyj/BookOasis_stable)
- [Readest](https://github.com/readest/readest)
- 플러그인은 [AGPL-3.0](LICENSE)으로 배포합니다. Readest 수정판은 원본 AGPL-3.0 고지와 하위 구성 요소 라이선스를 유지하며 전체 소스를 함께 제공합니다.
- 소스 변경과 파일 목록은 [변경 이력](CHANGELOG.md), [소스 조사](docs/SOURCE_AUDIT.ko.md)를 참고하세요.
