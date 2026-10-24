# b3 재빌드

전체 대응 소스 ZIP의 readest/가 저장소 루트다. 원본 커밋·서브모듈·의존성 잠금 파일과 b1의 Windows 교차 빌드 수정도 보존했다. 기존 bookoasis/BUILD-b1-b2-reference.ko.md의 SDK/JDK/NDK/워크스페이스 설치 과정을 따른다.

새 코드: OPDS 세션을 선택한 파일 단위의 재생 목록으로 열고, 현재 파일만 측정한다. AudiobookController의 playlist 옵션이 순서 재생·선택·실패/취소를 관리한다. OpdsTracksView가 재생 전/중 목록을 표시한다. 현재 파일 URL·시간은 library.json의 opdsAudioProgress에 저장한다. 파일 다운로드와 인증 처리는 앱의 기존 구현을 재사용한다. Rust 소스/Google 인증/클라우드 동기화 코드는 이번 b3에서 수정하지 않았다.

```sh
pnpm install --frozen-lockfile
pnpm --filter @readest/readest-app setup-vendors
cd apps/readest-app
pnpm test --run --config vitest.bookoasis.config.mts src/__tests__/services/opds src/__tests__/services/audiobook-controller.test.ts src/__tests__/services/audiobook-timeline.test.ts src/__tests__/app/player
pnpm lint
pnpm exec tauri android build --ci --apk -t aarch64 --config ../../bookoasis/tauri.bookoasis.conf.json
```

Node 22.23.4, JDK 17, NDK 28.2.13676358, Rust 1.99.1을 사용했다. Node 빌드에서 Windows 경로를 NODE_OPTIONS의 --require에 넣을 때 슬래시(/)로 표기한다. 이 PC의 hoisted 설치/foliate-js 테스트 별칭/일시적 mkdir 재시도는 b1/b2의 빌드 설정을 그대로 사용했다. 일반 개발 환경에서는 정상 심볼릭 링크 설치로 빌드할 수 있다.

Windows에서 Tauri가 Rust 빌드 완료 후 jniLibs 심볼릭 링크 생성만 실패하는 경우, 기존 BUILD.ko.md에 기록한 성공한 .so 복사 후 Gradle assembleUniversalRelease 절차를 쓴다. 새 프런트엔드를 포함한 Rust 라이브러리를 다시 컴파일해야 한다. b2의 .so를 재사용하면 새 화면이 포함되지 않는다.

버전 이름 0.12.16+bookoasis.3, Android versionCode 12018. 자신의 키로 서명한다. 원래 b1/b2의 서명 키는 소스 ZIP에 포함하지 않는다.
