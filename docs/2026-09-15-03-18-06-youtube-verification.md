# Aegisub YouTube verification

Recorded 2026-09-15-03-18-06 KST. Build-script fix: `6fd1aa9b5864cec73add0cfaed0506aaa802b6ce`; native binary source is the SHA below. The latest native source is SHA `861ee477d926b5b5b709180ed404a9af3c7f8ae1`, based on merged ARM64 SHA `5601ed225aef1ecf8bb58f737b4142883d603bd7`, and the current macOS ARM64 package is [2026-09-15-02-16-01-aegisub-youtube-arm64](../artifacts/2026-09-15-02-16-01-aegisub-youtube-arm64). The original checkout and supplied subtitle originals remain unchanged. See the [guide](2026-09-15-03-18-06-youtube-guide.md) for usage and limitations.

## Published subtitle and device result

The corrected Korean track was uploaded through the authorized signed-in Aside session and published to [Adorena](https://www.youtube.com/watch?v=jOYcCNgJDn0). Desktop playback shows all three colored lines. The user confirmed that iPhone flicker was gone at **28–31 seconds after reopening the video**. This is device/segment evidence, not a guarantee for all iOS versions or the entire video.

The position-corrected variant did not resolve the user's iPhone flicker, and the user still observed flicker in the second single-outline variant. The selected variant keeps one active caption per center/bottom region and combines simultaneous rows with line breaks. All **996 timing boundaries** retain the exact ordered original text/style spans, excluding inserted invisible separators. Karaoke color changes remain. Android fullscreen rows were already non-overlapping; the user accepts app-specific background/font differences.

- [Final files and hashes](../artifacts/2026-09-15-adrena/final-subtitles.json)
- [Boundary validation](../artifacts/2026-09-15-adrena/combined-lines-validation.json)
- [Desktop published result](../artifacts/2026-09-15-adrena/desktop-combined-29s.png)

The final YTT and imported editable ASS are stored beside the originals under `2026-09-15-아드레나-동시행묶음`. The imported ASS contains expanded color states, not the original authoring karaoke tags; keep the original ASS for timing edits. The posted YTT is the verified playback artifact.

## Resolution and tag-order experiments

Changing only PlayRes from 1920×1080 to 640×360 clamps the supplied positions to the lower-right corner. Resampling coordinates, font sizes, margins and border/shadow dimensions by one third produces **byte-identical YTT** to the original-resolution conversion. Thus 640×360 alone is not a fix for this file.

Moving `\pos` before or after the initial `\k` also produces byte-identical YTT in this converter: **614,468 bytes**, SHA-256 `d6b5477ffa8dec921227b1a2f96596a05b7f0b4d30e81c7df69d11e003b5e88f`. The original last row at 29 seconds already has `\pos` first. [Experiment evidence](../artifacts/2026-09-15-adrena/tag-order/2026-09-15-01-05-14-evidence.json).

## Native and packaged verification

- macOS package helper: **51 checks passed**, including 13 pinned upstream YTT goldens and 27 anchor/justification round trips. [Results](../artifacts/youtube-regression-final.json).
- The latest native macOS ARM64 package [2026-09-15-02-16-01-aegisub-youtube-arm64](../artifacts/2026-09-15-02-16-01-aegisub-youtube-arm64), for source SHA `861ee477d926b5b5b709180ed404a9af3c7f8ae1` based on merged ARM64 SHA `5601ed225aef1ecf8bb58f737b4142883d603bd7`, was directly launched with developer runtime variables removed and isolated settings. Under the Korean locale, GUI conversion and compatibility diagnostics were directly observed, including fade, transform and ytkt warnings in [mac-regex-diagnostics.png](../artifacts/2026-09-15-adrena/mac-regex-diagnostics.png). The sample converted 3 rows to 55 events and 22,904 bytes in **859 ms**. [QA record](../artifacts/2026-09-15-adrena/mac-package-qa.json). The prior 1,405 ms GUI observation and its [ready state](../artifacts/2026-09-15-adrena/mac-msvc-ready.jpg) remain historical; the **4-second video-QA** result was only the earlier **734 ms** observation from [the previous package](../artifacts/2026-09-15-01-00-46-aegisub-youtube-arm64), with its [earlier ready state](../artifacts/2026-09-15-adrena/mac-package-ready.jpg) and [video render](../artifacts/2026-09-15-adrena/mac-package-preview.jpg), and is not a latest-package result.
- Actual Windows 11 AMD64 helper: **16 smoke checks passed**, covering help, 13 goldens, Korean paths/import/source preservation, and rejected missing input. [Results](../artifacts/2026-09-15-adrena/windows-smoke-results.json).
- Actual Windows Chrome: the helper supplied the local YTT, received the matching response ACK, and displayed three colored rows. Its dedicated browser/profile was stopped and removed. [Status](../artifacts/2026-09-15-adrena/windows-player-status.txt).
- Native Windows GUI, installer and portable validation are pending. The [current CI run](https://github.com/Tygb99/Aegisub-arch1t3cht/actions/runs/34873355050) reports the standard Windows native build and all **354 C++ tests passed**, but the locked helper restore failed with `NU1004`; the native build artifact was preserved and downloaded. A separate actual-Windows build of the revised [PowerShell helper](../artifacts/2026-09-15-adrena/helper-native-build.json) using `-p:RuntimeIdentifier=win-x64` succeeded at **03:03 KST** with SDK **10.0.301**; `--help` exited 0 despite 16 upstream switch warnings. The CI installer remains unverified, and native GUI/portable QA is still pending while it is checked directly. The overall CI still has the old wx-master patch lane failing on its obsolete dependency patch, macOS 13 queued, and other macOS ARM64/Ubuntu jobs passing. The helper smoke checks and actual Chrome observation above do not certify native Windows GUI readiness.

## Limits

macOS minimum version is 26.0; signing is ad-hoc, without Developer ID notarization. Clean-machine Gatekeeper acceptance is untested. ASS preview is an approximation; independent multiline justification can differ and is diagnosed. The external desktop player requires Chrome/Edge and an existing matching manual caption track. Response ACK establishes byte identity, while screenshots and device feedback establish the observed display.
