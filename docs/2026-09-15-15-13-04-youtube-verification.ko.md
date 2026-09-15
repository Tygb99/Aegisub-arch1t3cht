# Aegisub YouTube 검증

기록: 2026-09-15-15-13-04 KST. 빌드 스크립트 수정 커밋은 `6fd1aa9b5864cec73add0cfaed0506aaa802b6ce`이며 네이티브 바이너리 소스는 아래 SHA입니다. 최신 네이티브 소스 SHA는 `861ee477d926b5b5b709180ed404a9af3c7f8ae1`이며, 병합된 ARM64 SHA `5601ed225aef1ecf8bb58f737b4142883d603bd7`를 기반으로 합니다. 현재 macOS ARM64 패키지는 [2026-09-15-02-16-01-aegisub-youtube-arm64](../artifacts/2026-09-15-02-16-01-aegisub-youtube-arm64)입니다. 원래 체크아웃과 제공된 자막 원본은 변경하지 않았습니다. 사용법과 제약은 [안내서](2026-09-15-15-13-04-youtube-guide.ko.md)를 참조하세요.

## 게시 자막과 기기 결과

승인된 Aside 로그인 세션에서 [아드레나](https://www.youtube.com/watch?v=jOYcCNgJDn0)의 한국어 자막을 업로드하고 게시했습니다. PC 재생에서 색이 있는 세 줄을 확인했습니다. 사용자는 **영상을 다시 연 뒤 28~31초에서 아이폰 깜박임이 없어졌다**고 확인했습니다. 해당 기기·구간의 결과이며 모든 iOS 버전이나 영상 전체를 보장하지 않습니다.

위치를 수정한 버전에서도 아이폰 깜박임은 해결되지 않았고, 두 번째 외곽선 하나 버전에서도 사용자는 깜박임을 계속 확인했습니다. 먼저 확인한 단일 외곽선 버전은 중앙/하단 영역마다 하나의 자막 블록만 활성화하고 동시에 표시되는 행을 줄바꿈으로 묶습니다. 삽입한 투명 구분자를 제외하고 **996개 시간 경계**에서 원래 텍스트·스타일 순서를 정확히 보존했습니다. 가라오케 색 변화도 유지합니다. 안드로이드는 전체화면에서 이미 겹치지 않았고, 사용자는 앱의 배경·글꼴 차이를 수용했습니다.

- [최종 파일과 해시](../artifacts/2026-09-15-adrena/final-subtitles.json)
- [시간 경계 검증](../artifacts/2026-09-15-adrena/combined-lines-validation.json)
- [게시 후 PC 화면](../artifacts/2026-09-15-adrena/desktop-combined-29s.png)

먼저 확인한 YTT와 가져온 편집용 ASS를 원본 옆에 `2026-09-15-아드레나-동시행묶음`으로 저장했습니다. 가져온 ASS에는 원래 가라오케 작성 태그 대신 펼쳐진 색 변화 상태가 들어 있으므로 타이밍 편집용 원본 ASS도 보관하세요. 실제 게시·재생을 검증한 파일은 YTT입니다.

## 그림자 복원 비교 결과

세 줄 묶음을 유지한 채 원래 네 겹 효과를 복원해 게시했고, 사용자가 아이폰 앱에서 **깜박임 없음**을 확인했습니다. 따라서 이번 사례에서 그림자 제거는 해결에 필요하지 않았습니다. 비교본은 1,009개 묶음 블록을 네 효과 층인 4,036개 블록으로 복원했으며 행·타이밍·색을 보존했습니다. 원래 효과를 복원한 YTT가 현재 게시본입니다. 모바일 브라우저 재생도 정상이라고 사용자가 보고했습니다. 이 결과를 모든 영상·기기에 일반화하지 않습니다. 이 행 묶음은 해당 자막 파일에 적용한 별도 처리이며 앱의 모든 변환에 자동 적용되는 기능은 아닙니다.

## 해상도와 태그 순서 실험

PlayRes 숫자만 1920×1080에서 640×360으로 바꾸면 제공된 좌표가 오른쪽 아래로 몰립니다. 좌표·글자 크기·여백·테두리와 그림자 치수까지 1/3로 리샘플링하면 원래 해상도에서 변환한 YTT와 **바이트 단위로 같습니다**. 따라서 이 파일에서 640×360 자체는 해결책이 아닙니다.

첫 `\k` 앞뒤로 `\pos` 순서를 바꿔도 이 변환기의 YTT는 완전히 같습니다. **614,468바이트**, SHA-256 `d6b5477ffa8dec921227b1a2f96596a05b7f0b4d30e81c7df69d11e003b5e88f`입니다. 원본의 29초 마지막 줄도 이미 `\pos`가 먼저였습니다. [실험 증거](../artifacts/2026-09-15-adrena/tag-order/2026-09-15-01-05-14-evidence.json).

## 네이티브·패키지 검증

- macOS 패키지 helper **51개 검사 통과**: 고정된 상류 YTT golden 13개와 앵커/정렬 왕복 27개 등을 포함합니다. [결과](../artifacts/youtube-regression-final.json).
- 최신 네이티브 macOS ARM64 패키지 [2026-09-15-02-16-01-aegisub-youtube-arm64](../artifacts/2026-09-15-02-16-01-aegisub-youtube-arm64)는 병합된 ARM64 SHA `5601ed225aef1ecf8bb58f737b4142883d603bd7`를 기반으로 한 최신 네이티브 소스 SHA `861ee477d926b5b5b709180ed404a9af3c7f8ae1`에 해당합니다. 개발자 런타임 변수를 제거하고 격리 설정으로 직접 실행했으며, 한글 로캘에서 GUI 변환과 호환성 진단을 직접 관찰했습니다. [mac-regex-diagnostics.png](../artifacts/2026-09-15-adrena/mac-regex-diagnostics.png)에 fade·transform·ytkt 경고가 기록되어 있습니다. 샘플 3행은 이벤트 55개, 22,904바이트로 변환됐고 **859ms**였습니다. [QA 기록](../artifacts/2026-09-15-adrena/mac-package-qa.json). 이전 1,405ms GUI 관찰과 [완료 화면](../artifacts/2026-09-15-adrena/mac-msvc-ready.jpg)은 과거 증거이며, **4초 영상 QA**는 [이전 패키지](../artifacts/2026-09-15-01-00-46-aegisub-youtube-arm64)에서만 수행한 과거 **734ms** 관찰이고 [이전 완료 화면](../artifacts/2026-09-15-adrena/mac-package-ready.jpg)과 [영상 화면](../artifacts/2026-09-15-adrena/mac-package-preview.jpg)이 이에 해당합니다. 최신 패키지 결과가 아닙니다.
- 실제 Windows 11 AMD64 helper **16개 스모크 검사 통과**: 도움말, golden 13개, 한글 경로·가져오기·원본 보존, 없는 입력 거부를 확인했습니다. [결과](../artifacts/2026-09-15-adrena/windows-smoke-results.json).
- 실제 Windows Chrome에서 로컬 YTT 응답의 일치하는 ACK를 받고 색이 있는 세 줄을 확인했습니다. 전용 브라우저와 임시 프로필은 종료·정리했습니다. [상태](../artifacts/2026-09-15-adrena/windows-player-status.txt).
- Windows portable 네이티브 GUI 검증을 완료했습니다. 실제 Windows 11 AMD64의 한글·공백 경로에서 ASS 열기, YouTube 변환, 호환성 진단, YTT·ASS·manifest 내보내기를 확인했습니다. 3행 → 55개 이벤트, 22,904바이트, 1,129ms였고 내보낸 YTT 해시가 manifest와 일치했습니다. [검증 기록](../artifacts/2026-09-15-adrena/windows-native-qa.json). 첫 대화상자는 이 표시 환경에서 수동으로 넓혀야 했습니다. 전체 설치 프로그램과 선택 코덱, 새 Windows의 VC 런타임 요구는 미검증입니다. CI의 Windows 네이티브 빌드·354개 C++ 테스트는 통과했으나 helper 잠금 복원은 NU1004로 실패했습니다. RuntimeIdentifier 수정 후 별도 실제 Windows helper 빌드와 16개 검사를 통과했습니다. 기존 wx-master 의존성 패치 실패는 남아 있으며 전체 CI 성공을 주장하지 않습니다.

## 제약

macOS 최소 버전은 26.0이며 ad-hoc 서명으로 Developer ID 공증이 없습니다. 새 컴퓨터의 Gatekeeper 허용은 검증하지 않았습니다. ASS 미리보기는 근사치이며 독립적인 여러 줄 정렬은 다를 수 있어 진단합니다. 외부 데스크톱 플레이어에는 Chrome/Edge와 언어가 맞는 기존 수동 자막 트랙이 필요합니다. 응답 ACK는 바이트 동일성, 화면과 기기 피드백은 관찰한 표시 결과를 증명합니다.
