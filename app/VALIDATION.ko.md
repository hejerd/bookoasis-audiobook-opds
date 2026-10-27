# 앱 b6 검증 결과

2026-10-26에 빌드한 b6-test1 APK를 이름만 바꿔 배포합니다. 새 APK 빌드나 새로운 실기 전체 검사를 했다는 의미는 아닙니다.

- 관련 테스트: 107개 파일, **883개 통과**, 262.96초.
- TypeScript와 Biome: 통과, 검사 대상 2,864개 파일.
- 짧은 MP3·M4B 샘플의 제한된 헤더 요청과 길이 파싱·취소 확인.
- 실제 서재/진행률 컴포넌트: 휴대폰 그리드·목록, 다크 모드, 태블릿 e-ink/RTL 렌더링 확인.
- Android 빌드, APK 서명, zipalign 16KB 정렬, 네이티브 ELF 정렬, 포함된 프런트엔드 확인 통과.
- 전체 Readest 테스트는 TTS paragraph boundary 테스트의 60초 시간 초과로 중단됐습니다. 관련 테스트 통과와 별개입니다.
- 모든 Android 기기의 소리·장시간 백그라운드·기기간 충돌을 검증한 것은 아닙니다. 사전 공개 버전입니다.

앱 ID `com.bilingify.readest.bookoasis`, 버전 `0.12.16+bookoasis.6`, versionCode `12021`, 최소 Android 8, ABI arm64-v8a. 기존 공개 b3와 같은 인증서로 서명했습니다.
