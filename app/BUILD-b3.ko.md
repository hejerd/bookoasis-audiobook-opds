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

## 공개 APK의 빌드 경로 정리

공개 APK는 Android 네이티브 라이브러리를 다시 컴파일하여 개인 PC의 소스·Cargo·Rustup 경로를 일반 빌드 경로로 치환했습니다. 실행 코드와 앱 ID·버전은 유지하고 이전 BookOasis 앱과 같은 인증서로 서명했습니다.

Windows의 Android 빌드 환경을 준비한 뒤 저장소 루트에서 다음을 먼저 실행하고 위 Android 빌드를 진행합니다. 스크립트는 소스 ZIP의 `bookoasis/`에 포함되어 있으며 실제 사용자 경로는 배포하지 않습니다.

```powershell
. ./bookoasis/set-path-remap.ps1
```

이 스크립트는 Rust의 `--remap-path-prefix`를 `CARGO_ENCODED_RUSTFLAGS`에 추가합니다. 컴파일러가 포함하는 소스 위치를 바꾸므로 의존성도 다시 컴파일됩니다. 패키징 후 APK 내부의 모든 파일을 풀어 개인 PC 경로·서버 식별자·개인키·토큰 패턴을 다시 검사합니다.

웹 화면 번들에 Webpack의 `import.meta.url`이 빌드 PC의 파일 URL로 남는 경우도 정리합니다. `next.config.mjs`가 `bookoasis/remap-client-build-paths.mjs`를 사용해 JavaScript 자산 안의 저장소 루트만 `file:///build/readest/`로 바꾸며, 상대 파일 경로와 일반 네트워크 URL은 유지합니다. Webpack의 내용 해시 계산 전에 적용합니다.

```sh
node --test bookoasis/remap-client-build-paths.test.mjs
```

공개 재빌드는 Rust의 소스 위치와 웹 화면의 파일 URL 모두를 검사했습니다. 오디오북 재생·인증·동기화 로직은 이 정리에서 변경하지 않았습니다.
