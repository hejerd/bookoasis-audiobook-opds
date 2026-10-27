# 개발·검증 자료

설치와 사용은 [README](../README.md)를 먼저 보세요.

저장소 루트의 `audiobook_opds.py`와 `__init__.py`, `VERSION`, `dashboard.html/css/js`가 설치되는 런타임입니다. 공식 `BaseMetadataProvider`의 general 시작 훅, `get_db_gateway('audiobook')`, 홈 위젯 확장을 사용합니다. 본체 코드·DB 구조를 변경하지 않습니다.

동기화는 `/opds/sync/v1`에서 기존 BookOasis 계정 인증과 권한을 적용합니다. 계정별 동기화 상태는 general DB의 기존 user_settings에, 웹 이어듣기는 기존 audiobook_progress와 track_progress에 저장합니다. GET에도 웹 기록 가져오기 등 동기화 상태 갱신이 포함될 수 있습니다. 홈 위젯 조회는 읽기 전용입니다.

테스트는 verification/plugin-tests.zip에 있습니다. 압축을 풀고 공식 BookOasis 소스와 플러그인 소스 경로를 명시합니다.

```sh
python -m pytest tests --bookoasis-source /path/to/BookOasis_stable --plugin-source /path/to/audiobook_opds
```

[플러그인 검증](VALIDATION.ko.md) · [공식 소스 확인 기록](SOURCE_AUDIT.ko.md) · [앱 빌드](../app/BUILD-b7.ko.md)
