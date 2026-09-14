# Aegisub YouTube 검증

기록: 2026-09-15-03-18-06 KST. 빌드 스크립트 수정 커밋은 `6fd1aa9b5864cec73add0cfaed0506aaa802b6ce`이며 네이티브 바이너리 소스는 아래 SHA입니다. 최신 네이티브 소스 SHA는 `861ee477d926b5b5b709180ed404a9af3c7f8ae1`이며, 병합된 ARM64 SHA `5601ed225aef1ecf8bb58f737b4142883d603bd7`를 기반으로 합니다. 현재 macOS ARM64 패키지는 [2026-09-15-02-16-01-aegisub-youtube-arm64](../artifacts/2026-09-15-02-16-01-aegisub-youtube-arm64)입니다. 원래 체크아웃과 제공된 자막 원본은 변경하지 않았습니다. 사용법과 제약은 [안내서](2026-09-15-03-18-06-youtube-guide.ko.md)를 참조하세요.

## 게시 자막과 기기 결과

승인된 Aside 로그인 세션에서 [아드레나](https://www.youtube.com/watch?v=jOYcCNgJDn0)의 한국어 자막을 업로드하고 게시했습니다. PC 재생에서 색이 있는 세 줄을 확인했습니다. 사용자는 **영상을 다시 연 뒤 28~31초에서 아이폰 깜박임이 없어졌다**고 확인했습니다. 해당 기기·구간의 결과이며 모든 iOS 버전이나 영상 전체를 보장하지 않습니다.

위치를 수정한 버전에서도 아이폰 깜박임은 해결되지 않았고, 두 번째 외곽선 하나 버전에서도 사용자는 깜박임을 계속 확인했습니다. 최종본은 중앙/하단 영역마다 하나의 자막 블록만 활성화하고 동시에 표시되는 행을 줄바꿈으로 묶습니다. 삽입한 투명 구분자를 제외하고 **996개 시간 경계**에서 원래 텍스트·스타일 순서를 정확히 보존했습니다. 가라오케 색 변화도 유지합니다. 안드로이드는 전체화면에서 이미 겹치지 않았고, 사용자는 앱의 배경·글꼴 차이를 수용했습니다.

- [최종 파일과 해시](../artifacts/2026-09-15-adrena/final-subtitles.json)
- [시간 경계 검증](../artifacts/2026-09-15-adrena/combined-lines-validation.json)
- [게시 후 PC 화면](../artifacts/2026-09-15-adrena/desktop-combined-29s.png)

최종 YTT와 가져온 편집용 ASS를 원본 옆에 `2026-09-15-아드레나-동시행묶음`으로 저장했습니다. 가져온 ASS에는 원래 가라오케 작성 태그 대신 펼쳐진 색 변화 상태가 들어 있으므로 타이밍 편집용 원본 ASS도 보관하세요. 실제 게시·재생을 검증한 파일은 YTT입니다.

## 해상도와 태그 순서 실험

PlayRes 숫자만 1920×1080에서 640×360으로 바꾸면 제공된 좌표가 오른쪽 아래로 몰립니다. 좌표·글자 크기·여백·테두리와 그림자 치수까지 1/3로 리샘플링하면 원래 해상도에서 변환한 YTT와 **바이트 단위로 같습니다**. 따라서 이 파일에서 640×360 자체는 해결책이 아닙니다.

첫 `\k` 앞뒤로 `\pos` 순서를 바꿔도 이 변환기의 YTT는 완전히 같습니다. **614,468바이트**, SHA-256 `d6b5477ffa8dec921227b1a2f96596a05b7f0b4d30e81c7df69d11e003b5e88f`입니다. 원본의 29초 마지막 줄도 이미 `\pos`가 먼저였습니다. [실험 증거](../artifacts/2026-09-15-adrena/tag-order/2026-09-15-01-05-14-evidence.json).

## 네이티브·패키지 검증

- macOS 패키지 helper **51개 검사 통과**: 고정된 상류 YTT golden 13개와 앵커/정렬 왕복 27개 등을 포함합니다. [결과](../artifacts/youtube-regression-final.json).
- 최신 네이티브 macOS ARM64 패키지 [2026-09-15-02-16-01-aegisub-youtube-arm64](../artifacts/2026-09-15-02-16-01-aegisub-youtube-arm64)는 병합된 ARM64 SHA `5601ed225aef1ecf8bb58f737b4142883d603bd7`를 기반으로 한 최신 네이티브 소스 SHA `861ee477d926b5b5b709180ed404a9af3c7f8ae1`에 해당합니다. 개발자 런타임 변수를 제거하고 격리 설정으로 직접 실행했으며, 한글 로캘에서 GUI 변환과 호환성 진단을 직접 관찰했습니다. [mac-regex-diagnostics.png](../artifacts/2026-09-15-adrena/mac-regex-diagnostics.png)에 fade·transform·ytkt 경고가 기록되어 있습니다. 샘플 3행은 이벤트 55개, 22,904바이트로 변환됐고 **859ms**였습니다. [QA 기록](../artifacts/2026-09-15-adrena/mac-package-qa.json). 이전 1,405ms GUI 관찰과 [완료 화면](../artifacts/2026-09-15-adrena/mac-msvc-ready.jpg)은 과거 증거이며, **4초 영상 QA**는 [이전 패키지](../artifacts/2026-09-15-01-00-46-aegisub-youtube-arm64)에서만 수행한 과거 **734ms** 관찰이고 [이전 완료 화면](../artifacts/2026-09-15-adrena/mac-package-ready.jpg)과 [영상 화면](../artifacts/2026-09-15-adrena/mac-package-preview.jpg)이 이에 해당합니다. 최신 패키지 결과가 아닙니다.
- 실제 Windows 11 AMD64 helper **16개 스모크 검사 통과**: 도움말, golden 13개, 한글 경로·가져오기·원본 보존, 없는 입력 거부를 확인했습니다. [결과](../artifacts/2026-09-15-adrena/windows-smoke-results.json).
- 실제 Windows Chrome에서 로컬 YTT 응답의 일치하는 ACK를 받고 색이 있는 세 줄을 확인했습니다. 전용 브라우저와 임시 프로필은 종료·정리했습니다. [상태](../artifacts/2026-09-15-adrena/windows-player-status.txt).
- 네이티브 Windows GUI·설치 프로그램·portable 검증은 대기 중입니다. [현재 CI 실행](https://github.com/Tygb99/Aegisub-arch1t3cht/actions/runs/34873355050)은 standard Windows 네이티브 빌드와 C++ 테스트 **354개가 통과**했지만 helper 잠금 복원은 `NU1004`로 실패했고, 네이티브 빌드 artifact는 보존·다운로드되었습니다. 별도 실제 Windows에서 `-p:RuntimeIdentifier=win-x64`를 사용하는 수정한 [PowerShell helper](../artifacts/2026-09-15-adrena/helper-native-build.json)는 **03:03 KST**에 SDK **10.0.301**로 빌드에 성공했고, 16개 upstream switch 경고가 있었지만 `--help`는 exit 0이었습니다. CI 설치 프로그램 성공은 아직 검증되지 않았으며, 네이티브 GUI와 portable QA는 직접 확인 중이므로 대기 상태입니다. 전체 CI에서는 기존 wx-master 패치 작업이 낡은 의존성 패치로 실패하고 macOS 13은 대기 중이며, 다른 macOS ARM64와 Ubuntu job은 통과했습니다. 위의 helper 스모크 검사와 실제 Chrome 확인은 네이티브 Windows GUI가 준비되었다는 뜻이 아닙니다.

## 제약

macOS 최소 버전은 26.0이며 ad-hoc 서명으로 Developer ID 공증이 없습니다. 새 컴퓨터의 Gatekeeper 허용은 검증하지 않았습니다. ASS 미리보기는 근사치이며 독립적인 여러 줄 정렬은 다를 수 있어 진단합니다. 외부 데스크톱 플레이어에는 Chrome/Edge와 언어가 맞는 기존 수동 자막 트랙이 필요합니다. 응답 ACK는 바이트 동일성, 화면과 기기 피드백은 관찰한 표시 결과를 증명합니다.
