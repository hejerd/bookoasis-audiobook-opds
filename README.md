# BookOasis 오디오북 클라이언트 연결 플러그인

**기존 BookOasis 서버에 추가해, 오디오북 클라이언트 앱에서 서버의 책을 찾아 듣게 해주는 플러그인입니다.**

서버에는 `audiobook_opds` 플러그인을 설치하고, Android 휴대폰·태블릿에는 **Readest BookOasis** 앱을 설치합니다. 앱에 서버의 OPDS 주소와 BookOasis 계정을 등록하면 연결됩니다.

**BookOasis 서버 → audiobook_opds 플러그인 → Readest BookOasis 앱 → 오디오북 재생**

## 할 수 있는 것

- BookOasis에 등록된 오디오북을 카테고리별로 탐색
- 표지와 제목을 그리드로 표시하고 제목순·최신 추가순 등으로 정렬
- 책을 열어 회차 목록에서 원하는 회차 선택
- 이어듣기, 이전·다음 회차 이동, 다음 회차 자동 재생
- MP3·M4A·M4B 스트리밍과 다운로드

기존 BookOasis 계정과 라이브러리 접근 권한을 사용합니다. Readest BookOasis는 이 연결에 맞춰 수정한 **비공식 Android 앱**이며, 공식 Readest와 별도로 설치됩니다.

## 준비할 것

| 설치할 곳 | 필요한 것 |
| --- | --- |
| 서버 | 오디오북이 등록되어 있는 BookOasis, 플러그인 폴더와 Docker 설정을 수정할 권한 |
| 휴대폰·태블릿 | Android 8 이상, arm64-v8a 기기 |
| 연결 정보 | 휴대폰에서 접속할 서버 주소, 기존 BookOasis 사용자 이름·비밀번호 |

서버 플러그인은 BookOasis dashboard 3.0.2 환경에서 확인했습니다.

## 다운로드

| 파일 | 설치할 곳·용도 |
| --- | --- |
| [audiobook_opds-0.4.2.zip](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.2/audiobook_opds-0.4.2.zip) | BookOasis 서버용 플러그인 |
| [Readest BookOasis APK](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.1-b3/Readest-BookOasis-0.12.16-b3-arm64.apk) | Android 휴대폰·태블릿에 설치 |
| [앱 전체 수정 소스](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.1-b3/Readest-BookOasis-0.12.16-b3-source.zip) | 개발·수정용이며 앱 설치에는 필요 없음 |
| [플러그인 SHA256](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.2/SHA256SUMS.txt) | 플러그인 ZIP 확인용 |

플러그인게시판을 사용한다면 **아래 Git URL로 서버에 설치하고 APK만 받으면 됩니다.** ZIP은 수동 설치용입니다. 이 버전은 사전 공개 버전입니다. [플러그인 0.4.2 릴리스](https://github.com/hejerd/bookoasis-audiobook-opds/releases/tag/v0.4.2)

## 1. 서버에 플러그인 설치

### 플러그인게시판에서 Git URL로 설치

1. BookOasis의 **플러그인게시판 → Git 저장소 URL 설치**에 다음 주소를 붙여넣습니다.

   ```text
   https://github.com/hejerd/bookoasis-audiobook-opds
   ```

2. **Git 설치**를 누릅니다. 저장소 이름과 관계없이 플러그인은 `audiobook_opds` 폴더에 설치됩니다.
3. 아래의 **Docker 포트 추가**와 **BookOasis에서 서비스 켜기**를 진행합니다. 플러그인게시판에서 설치해도 Docker 포트는 별도로 추가해야 합니다.

공개 저장소이므로 GitHub 토큰은 필수가 아닙니다. 이후 플러그인게시판에서 업데이트할 수 있습니다. 이 방식은 플러그인게시판 2.52.0의 설치 소스를 기준으로 검사했습니다.

### ZIP으로 수동 설치하는 경우

1. **[플러그인 ZIP 다운로드](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.2/audiobook_opds-0.4.2.zip)** 후 압축을 풉니다.
2. 압축 안의 `plugins/metadata/audiobook_opds` 폴더를 서버의 BookOasis 플러그인 폴더에 복사합니다.
3. 최종 파일 위치가 아래와 같으면 됩니다. `audiobook_opds` 폴더가 두 번 중첩되지 않도록 확인하세요.

```text
BookOasis 플러그인 폴더/
└── metadata/
    └── audiobook_opds/
        ├── __init__.py
        ├── audiobook_opds.py
        └── VERSION
```

Docker를 사용한다면 컨테이너의 `/app/plugins`에 연결된 **서버 쪽 폴더**에 넣습니다. [폴더 위치 확인 방법](docs/INSTALL.ko.md#1-플러그인-파일-넣기)

### Docker 포트 추가

이 플러그인은 OPDS 연결에 **5941 포트**를 사용합니다. 기존 BookOasis 웹 화면 포트와 함께 사용할 수 있도록 `docker-compose.yml`의 BookOasis 서비스 `ports` 목록에 다음 한 줄을 추가합니다.

```yaml
- "5941:5941"
```

기존 포트·볼륨·환경 변수는 그대로 두고, Compose 파일이 있는 폴더에서 다음을 실행합니다. 예시 서비스 이름은 `bookoasis`입니다.

```bash
docker compose up -d bookoasis
```

이미 `5941:5941`이 설정되어 있다면 파일 복사 후 BookOasis 컨테이너만 재시작하면 됩니다. **서버 OS를 재부팅할 필요는 없습니다.**

기존에 5931로 사용했다면 업데이트 후에도 저장된 값은 유지됩니다. 포트를 옮기려면 [5931에서 5941로 전환](docs/INSTALL.ko.md#기존-5931에서-5941로-옮기기)을 따라 설정과 매핑을 함께 바꿉니다.

## 2. BookOasis에서 서비스 켜기

1. BookOasis에 **관리자 계정**으로 접속합니다.
2. **일반 도서 → 환경설정 → 플러그인 설정**에서 **오디오북 OPDS**를 찾습니다.
3. 플러그인 활성화 스위치를 켭니다.
4. **OPDS 서비스 시작 → 사용**을 체크하고 아래 값을 확인합니다.
5. **설정 저장**을 누릅니다.

| 설정 항목 | 처음 설치할 때 입력할 값 |
| --- | --- |
| 수신 주소 | `0.0.0.0` |
| 컨테이너 내부 포트 | `5941` |
| 앱에서 접속할 기본 URL | 비워두기 |
| 페이지당 목록 항목 수 | `30` |
| 카탈로그 제목 | `BookOasis Audiobooks` 또는 원하는 이름 |

휴대폰 브라우저에서 `http://서버주소:5941/opds`를 열어 보세요. BookOasis 계정으로 인증한 뒤 XML 형식의 목록이 보이면 서버 준비가 끝난 것입니다.

## 3. Android 앱 설치

**[Readest BookOasis APK 다운로드](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.4.1-b3/Readest-BookOasis-0.12.16-b3-arm64.apk)** 후 휴대폰·태블릿에서 엽니다. Android가 해당 브라우저·파일 앱의 설치 허용을 요구하면 허용한 뒤 설치합니다.

앱 이름은 **Readest BookOasis**입니다. 공식 Readest가 설치되어 있어도 함께 설치할 수 있습니다. 기존 Readest BookOasis를 사용 중이면 삭제하지 않고 APK를 열어 업데이트합니다.

## 4. 앱에 내 서버 등록

1. **Readest BookOasis**를 실행합니다.
2. 서재 위쪽 **`+` → 온라인 라이브러리**를 엽니다. 기기에 따라 **OPDS 카탈로그**로 표시될 수 있습니다.
3. **내 카탈로그 → 카탈로그 추가**를 누릅니다.
4. 다음 내용을 입력하고 **카탈로그 추가**를 누릅니다.

| 앱 입력 항목 | 입력 예시 |
| --- | --- |
| 카탈로그 이름 | `내 BookOasis 오디오북` |
| OPDS URL | `http://서버주소:5941/opds` |
| 사용자 이름 | BookOasis에 로그인할 때 쓰는 사용자 이름 |
| 비밀번호 | 해당 BookOasis 계정의 비밀번호 |

예를 들어 집 안 서버 주소가 `192.168.1.10`이면 `http://192.168.1.10:5941/opds`를 입력합니다. 휴대폰과 서버가 같은 네트워크에 있어야 이 주소로 접속할 수 있습니다.

앱의 사용자 이름·비밀번호 칸에 ‘선택 사항’이라고 표시되어도 **이 플러그인에 연결할 때는 둘 다 입력해야 합니다.** OPDS 연결에 Readest 계정이나 Google 로그인은 필요하지 않습니다.

## 5. 책 고르고 듣기

1. **내 카탈로그**에서 방금 등록한 서버를 엽니다.
2. 카테고리를 고르면 책 표지와 제목이 나옵니다.
3. 원하는 책을 열고 **재생**을 누릅니다.
4. 여러 회차로 된 책은 **회차 목록**에서 듣고 싶은 회차를 선택합니다. 한 파일로 된 책은 바로 플레이어로 이동합니다.
5. 재생 중 **회차 목록**, 이전·다음 버튼으로 회차를 바꿀 수 있습니다. 다시 열 때는 **재개**로 이어듣습니다.

정렬 메뉴에서 **제목 가나다순 / 제목 역순 / 최신 추가순 / 오래된 추가순 / 최근 수정순**을 고를 수 있습니다. 재생 시간과 탐색 막대는 현재 회차 기준입니다.

## 집 밖에서도 접속하려면

휴대폰에서 접근할 수 있는 외부 주소가 필요합니다. HTTPS 리버스 프록시를 사용한다면 OPDS용 도메인을 서버의 **5941 포트**로 연결하고, 앱에는 `https://audio.example.com/opds` 형태로 등록합니다.

이때 플러그인의 **앱에서 접속할 기본 URL**에는 `https://audio.example.com`을 입력합니다. 이 설정에는 끝에 `/opds`를 붙이지 않습니다. 기존 BookOasis 웹 화면만 외부에 연결되어 있다면 OPDS용 연결도 추가해야 합니다. [주소와 포트 설정 자세히 보기](docs/INSTALL.ko.md#외부에서-접속하기)

## 잘 안 될 때

| 증상 | 확인할 것 |
| --- | --- |
| 오디오북 OPDS가 설정에 안 보임 | 파일 위치가 `plugins/metadata/audiobook_opds/`인지 확인하고 BookOasis 재시작 |
| 주소에 연결할 수 없음 | `5941:5941`, OPDS 서비스 사용 체크, 서버 주소와 방화벽 확인 |
| 인증 실패 | BookOasis 계정·비밀번호 확인. 기본 비밀번호 상태라면 BookOasis에서 변경 후 사용 |
| 카테고리가 비어 있음 | BookOasis의 오디오북 등록 상태와 해당 계정의 라이브러리 접근 권한 확인 |
| 책은 나오는데 재생 안 됨 | 서버에서 원본 파일을 읽을 수 있는지 확인하고 Readest BookOasis 앱으로 재생 |

[서버 설치 자세히 보기](docs/INSTALL.ko.md) · [앱 설치와 사용 자세히 보기](app/INSTALL.ko.md)

## 소스와 라이선스

이 프로젝트는 [BookOasis](https://github.com/leeyj/BookOasis_stable)와 [Readest](https://github.com/readest/readest)의 비공식 확장입니다. 플러그인과 앱 수정판은 AGPL-3.0 라이선스를 따르며, 원본 고지를 유지합니다. 앱 APK와 해당 버전의 전체 수정 소스를 함께 제공합니다. GitHub가 자동 생성하는 `Source code` ZIP은 이 배포 저장소이고, 앱 전체 소스는 위의 별도 `b3-source.zip`입니다.

[라이선스](LICENSE) · [변경 이력](CHANGELOG.md) · [개발·검증 자료](docs/DEVELOPMENT.ko.md)
