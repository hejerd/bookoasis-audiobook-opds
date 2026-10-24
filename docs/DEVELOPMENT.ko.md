# 개발·검증 자료

처음 설치하는 사용자는 [설치와 연결 안내](../README.md)를 참고하세요. 이 문서는 소스 수정·빌드·검증에 필요한 자료를 모읍니다.

## 소스 위치

- 서버 플러그인: `plugins/metadata/audiobook_opds/`
- 서버 검사와 직접 생성한 2초 샘플: `tests/`
- 앱 전체 대응 소스: 릴리스의 `Readest-BookOasis-0.12.16-b3-source.zip` (APK와 함께 게시 예정)
- `app/readest-playlist-b3.patch`는 b2에서 b3로의 변경만 포함합니다. 전체 앱 소스는 별도 소스 ZIP을 사용합니다.

## 기준과 문서

- BookOasis dashboard 3.0.2 / 공식 커밋 `f4f80943bc46e8b673674b88bc40fc16bfafbd98`
- Readest 0.12.16 / 공식 커밋 `27694ba28b590cfb6c4c88092b73d31ed1338de9`
- [플러그인 API 조사](SOURCE_AUDIT.ko.md)
- [플러그인 검증 결과](VALIDATION.ko.md)
- [앱 검증 결과](../app/VALIDATION.ko.md)
- [앱 빌드 안내](../app/BUILD-b3.ko.md)

## 플러그인 검사 실행

```bash
python -m pytest tests --bookoasis-source /path/to/BookOasis_stable -q
```

테스트 의존성은 Flask, Werkzeug, Pillow, requests, python-dotenv, mutagen, pytest, imageio-ffmpeg 및 BookOasis 실행 의존성입니다. 이 명령과 의존성 설치는 개발용이며 플러그인 사용자가 실행할 단계가 아닙니다.

## 확인한 범위

- 플러그인: 초기 171개 검사 통과 + 변경된 피드 계약 검사 1개 수정 후 재실행 통과로 고유 검사 172개 통과.
- 실제 서버: 읽기 전용 검사로 450권의 목록·상세 회차 일치, 정렬 75개, 표지 3개, 음원 2개의 HEAD 200·Range 206 확인.
- 앱: 관련 회귀 291개, TypeScript, 전체 lint, 프런트엔드·Android 빌드, APK 서명과 정렬 검사 통과.
- 한계: b3 Android 실기 소리·백그라운드·재생 시작 지연은 이 빌드에서 확인하지 못했습니다. 전체 원본 테스트는 범위 밖 실패와 진행 정지로 종료했고 전체 통과를 주장하지 않습니다. MariaDB 실기 검증은 하지 않았습니다.

소스·빌드·검증 기록과 설치 사용자 안내를 구분하여 보관합니다.
