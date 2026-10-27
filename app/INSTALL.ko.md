# Android 앱 설치와 연결

1. Android 8 이상 arm64-v8a 기기에서 [b6 APK](https://github.com/hejerd/bookoasis-audiobook-opds/releases/download/v0.5.2-b6/Readest-BookOasis-0.12.16-b6-arm64.apk)를 받습니다.
2. APK를 열어 **Readest BookOasis**를 설치합니다. 기존 BookOasis b3~b6 앱은 삭제하지 않고 업데이트합니다. 공식 Readest와는 별도로 설치됩니다.
3. 서재의 **+ → 온라인 라이브러리(OPDS 카탈로그) → 내 카탈로그 → 카탈로그 추가**를 엽니다.
4. `http://서버주소:5941/opds` 또는 자신의 HTTPS OPDS 주소와 BookOasis 사용자 이름·비밀번호를 입력합니다. Google/Readest 로그인은 필요하지 않습니다.
5. 서버를 열고 카테고리 → 책 → 재생 → 회차를 선택합니다. 중간 회차부터 시작할 수 있습니다.

플러그인 **0.5.2**와 함께 사용하세요. 같은 BookOasis 서버·계정의 재생목록과 회차·위치를 자동 동기화합니다. 앱의 작은 동기화 아이콘에서 상태를 확인하며, 따로 누를 필요는 없습니다. 웹에서 재생한 기록도 가져옵니다.

앱의 진행률은 전체 회차에서의 현재 위치입니다. 회차 길이가 전부 확인되면 전체 시간과 남은 시간을 표시하며, 확인 전에는 회차 기준 근사값임을 표시합니다. 하단 탐색 막대는 현재 회차 기준입니다.

기존 b6-test1을 설치했다면 이번 APK는 동일한 파일이므로 다시 설치할 필요가 없습니다. 앱 데이터와 계정은 유지됩니다. 두 기기를 동시에 재생할 때는 마지막 저장 위치를 확인하세요.

[서버 설치](../docs/INSTALL.ko.md) · [전체 사용 안내](../README.md) · [검증 범위](VALIDATION.ko.md)
