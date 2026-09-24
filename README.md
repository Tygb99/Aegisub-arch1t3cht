# Aegisub

바이너리 파일 및 일반 정보는 [홈페이지](http://aegisub.org)를 참조하십시오.

버그 트래커는 https://github.com/TypesettingTools/Aegisub/issues에서 확인할 수 있습니다.

지원 관련 문의는 [디스코드](https://discord.com/invite/AZaVyPr) 또는 [IRC](irc://irc.rizon.net/aegisub)에서 받으실 수 있습니다.

## YouTube 자막 연동

이 포크는 기존 ASS 편집, 오디오 타이밍, Lua 자동화 작업 흐름은 그대로 두고, ASS 자막을 YouTube 자막 형식(YTT/SRV3)으로 변환하고 확인하는 기능을 추가합니다. 대상 플랫폼은 macOS ARM64(Apple Silicon, macOS 26 이상)와 Windows x86_64입니다.

**주요 기능**

- **변환:** 편집 중인 ASS를 YTT로 변환합니다. 편집하면 이전 결과를 무효화하고 잠시 뒤 백그라운드에서 다시 변환합니다.
- **호환성 진단:** YouTube에서 다르게 보일 수 있는 태그와 효과를 경고합니다. 진단 항목을 더블클릭하면 해당 자막 행으로 이동합니다.
- **근사 미리보기:** 생성된 YTT를 다시 읽어 영상 화면에 근사치로 표시하고, 원본 ASS 화면과 바꿔 가며 비교할 수 있습니다. 실제 YouTube 렌더링과 픽셀 단위로 일치하지는 않습니다.
- **실제 YouTube 플레이어 확인(선택):** 별도로 설치한 Chrome(Windows는 Edge도 가능)을 전용 창으로 띄워, 공개 영상의 기존 수동 자막 트랙 요청에 로컬 YTT를 응답합니다. 자막을 업로드하지 않으며, 프록시나 인증서 설치도 쓰지 않습니다.
- **선택 행 효과와 출력 프로필:** 페이드, 변형, 가라오케 같은 효과를 선택한 행에 넣을 수 있고(실행 취소 가능), 크기·위치 보정과 모바일용 단순화 프로필을 고를 수 있습니다.
- **내보내기와 가져오기:** `result.ytt`, 설정이 포함된 `source.ass`, `compatible.srt`, 변환 manifest를 한 번에 내보낼 수 있습니다. 반대로 YTT/SRV3를 편집용 ASS로 가져올 수도 있습니다.

**사용 방법**

1. ASS 자막과 영상을 엽니다.
2. **파일 → YouTube**를 엽니다. 변환 설정, 선택 행 효과, 호환성 진단이 이 대화상자에 있습니다.
3. 변환이 끝나면 `영상 화면에서 YouTube 변환 결과 보기 (시각적 근사치)`를 켜서 결과를 비교합니다.
4. 경고를 확인한 뒤 `내보내기 묶음…`으로 결과를 저장합니다.
5. 실제 플레이어로 확인하려면 공개 watch URL과 기존 수동 자막 트랙의 언어 코드를 넣고 `실제 플레이어 시작`을 누릅니다. 다시 변환한 뒤에는 CC를 껐다 켜야 새 자막이 적용됩니다.

변환 설정은 ASS의 `[Script Info]`에 저장되므로, 설정을 남기려면 ASS 파일을 저장해야 합니다. 편집 원본은 ASS로 유지하고 YTT는 변환 결과로 다루세요.

**설치와 실행**

- **Windows:** 설치 프로그램과 portable 묶음에는 `aegisub.exe` 옆 `youtube\` 폴더에 self-contained 변환 helper가 포함됩니다. .NET을 따로 설치할 필요는 없지만 `youtube` 폴더 전체를 `aegisub.exe` 옆에 두어야 합니다.
- **macOS:** `Aegisub YouTube.app`에 helper가 포함되어 있어 Rosetta나 .NET을 설치할 필요가 없습니다. 앱은 ad-hoc 서명이며 Apple 공증을 받지 않았으므로, 처음 실행할 때 **시스템 설정 → 개인정보 보호 및 보안**에서 허용해야 할 수 있습니다.
- 브라우저가 기본 위치에 없으면 Aegisub을 실행하기 전에 환경 변수 `AEGISUB_YOUTUBE_CHROME`에 브라우저 실행 파일의 전체 경로를 지정하세요.

**제한 사항**

- 미리보기는 근사치입니다. 데스크톱, Android, iOS 플레이어는 배경색과 글꼴을 서로 다르게 표시할 수 있습니다. 게시하기 전에 대상 기기에서 직접 확인하세요.
- `\ytju0`~`\ytju2` 정렬 태그는 이 프로젝트의 확장 태그라서 다른 ASS 렌더러는 지원하지 않습니다.
- SRT 내보내기에는 스타일, 위치, 효과가 보존되지 않습니다.

**빌드**

helper를 빌드하려면 .NET SDK 10.0.301 또는 그 이후 패치 버전(`tools/youtube/global.json`)이 필요합니다.

```powershell
# Windows: 설치 프로그램과 portable 패키징이 쓰는 위치로 helper 게시
.\tools\youtube-build.ps1 -OutputDirectory build/youtube
```

```bash
# macOS ARM64: 네이티브 앱과 helper를 빌드하고 패키지 생성
bash tools/youtube-package.sh
# helper만 다시 빌드하고 회귀 검사 실행
bash tools/youtube-build.sh
ruby tools/youtube-test.rb
```

변환기는 [arcusmaximus/YTSubConverter](https://github.com/arcusmaximus/YTSubConverter)를 고정된 커밋으로 사용하고 이 프로젝트의 패치를 적용합니다. 변환기에는 MIT 라이선스가 적용되며, 고지는 `tools/youtube/patches/YTSubConverter-LICENSE`에 있습니다.

자세한 사용법과 동작 원리는 [YouTube 사용 안내](docs/2026-09-15-15-13-04-youtube-guide.ko.md)([English](docs/2026-09-15-15-13-04-youtube-guide.md))를, 검증 기록은 [검증 문서](docs/2026-09-15-15-13-04-youtube-verification.ko.md)를 참조하세요.

## 라이선스

이 저장소의 모든 파일은 다양한 GPL 호환 BSD 스타일 라이선스에 따라 배포됩니다. 자세한 내용은 라이선스 및 개별 소스 파일을 참조하십시오.
공식 윈도 및 OS X 빌드는 fftw3를 포함하고 있으므로 GPLv2 라이선스를 따릅니다.
