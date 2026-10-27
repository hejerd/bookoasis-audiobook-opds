# Readest BookOasis b7 빌드

전체 대응 소스 ZIP의 `readest/`가 루트입니다. 원본 Readest 커밋은 `27694ba28b590cfb7c4c88092b73d31ed1338de9`이며, 고정 하위 모듈 소스와 의존성 잠금 파일을 포함합니다. `bookoasis/source-manifest.json`에 하위 모듈 커밋과 변경 파일 해시를 기록했습니다.

## 준비

실제 빌드 도구: Node 22.23.4, pnpm 11.1.1, JDK 17, Rust 1.99.1, Android SDK/Build Tools 36.0.0, NDK 28.2.13676358. Rust target `aarch64-linux-android`를 설치하고 JAVA_HOME, ANDROID_HOME, NDK_HOME을 자신의 설치 경로로 설정합니다.

```sh
pnpm install --frozen-lockfile
pnpm --filter @readest/readest-app setup-vendors
```

Windows에서는 심볼릭 링크를 지원하는 개발 환경을 권장합니다. 이 빌드는 hoisted 의존성 설치와 Webpack을 사용했습니다. 저장소 루트에서 `. ./bookoasis/set-path-remap.ps1`을 실행하면 Rust에 개인 빌드 경로가 남지 않도록 치환합니다. `next.config.mjs`는 `bookoasis/remap-client-build-paths.mjs`를 사용해 웹 자산의 로컬 파일 URL도 치환합니다.

## Android 빌드

```sh
cd apps/readest-app
pnpm exec tauri android build --ci --apk -t aarch64 --config ../../bookoasis/tauri.bookoasis.conf.json
```

설정 파일의 앱 이름은 `Readest BookOasis`, 버전은 `0.12.16+bookoasis.7`, versionCode는 `12022`입니다. Android 앱 ID는 `com.bilingify.readest.bookoasis`이고 Kotlin namespace는 원래 값을 유지합니다. 생성된 Android Gradle 파일·리소스·tauri.properties도 소스에 포함했습니다. `tauri android init`을 다시 실행해 덮어쓰는 경우 이 수정본을 복원하세요.

개인 서명 키는 포함하지 않습니다. `src-tauri/gen/android/keystore.properties`에 자신의 키를 설정하거나 unsigned APK를 apksigner로 서명합니다. 다른 키로 서명한 APK로는 공개 APK에 덮어쓰기 업데이트할 수 없습니다.

출력: `src-tauri/gen/android/app/build/outputs/apk/universal/release/app-universal-release.apk`.

## 실제 Windows 빌드에서 사용한 대체 조립

프런트엔드를 먼저 `pnpm exec dotenv -e .env.tauri -- next build --webpack`으로 빌드한 뒤, Tauri 설정의 `build.beforeBuildCommand`만 빈 문자열로 바꾼 설정으로 네이티브 빌드를 실행했습니다. 기본 설정 한 번으로 빌드해도 같은 소스를 사용합니다.

Rust가 `Finished release`로 완료된 뒤 **jniLibs 심볼릭 링크 생성만 실패**한 경우에만 아래를 사용합니다. 방금 빌드한 라이브러리인지 확인하고 진행해야 합니다.

```powershell
$taskTarget=if ($env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR } else { (Resolve-Path ../../target).Path }
$taskNative=Join-Path $taskTarget 'aarch64-linux-android/release/libreadestlib.so'
$taskJni='src-tauri/gen/android/app/src/main/jniLibs/arm64-v8a'
New-Item -ItemType Directory -Force -Path $taskJni | Out-Null
Copy-Item -LiteralPath $taskNative -Destination "$taskJni/libreadestlib.so" -Force
Push-Location src-tauri/gen/android
./gradlew.bat :app:assembleUniversalRelease -PtargetList=aarch64 -ParchList=arm64 -PabiList=arm64-v8a -x :app:rustBuildArm64Release --no-daemon --max-workers=3
Pop-Location
```

빌드 중 일시적 Windows mkdir 오류가 발생하면 포함된 `bookoasis/windows-fs-retry.cjs`를 Node preload로 사용할 수 있습니다. Rust의 Windows→Android 교차 빌드용 `turso_ext` 수정은 `bookoasis/vendor/turso_ext`와 Cargo.toml의 patch에 포함되어 있습니다. 상위 프로젝트와 각 의존성의 라이선스를 유지합니다.

## 검사

앱 폴더에서 `pnpm exec tsc --noEmit`, `pnpm lint`, `pnpm test --run --config vitest.bookoasis.config.mts`를 사용할 수 있습니다. 전체 테스트의 문서·사전 처리 실패, TTS 시간 초과, 실행 환경 문제는 [검증 결과](VALIDATION.ko.md)에 기록했습니다. 전체 통과를 주장하지 않습니다.

루트에서 `node --test bookoasis/remap-client-build-paths.test.mjs`로 경로 치환을 검사할 수 있습니다. 배포 APK는 apksigner verify, zipalign의 16KB 검사, 압축 내부 개인정보 패턴 검사를 수행했습니다. 소스 ZIP에는 node_modules, 빌드 산출물, 개인 키, 실제 서버 DB를 넣지 않습니다.
