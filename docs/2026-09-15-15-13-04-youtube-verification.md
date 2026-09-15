# Aegisub YouTube verification

Recorded 2026-09-15-15-13-04 KST. Build-script fix: `6fd1aa9b5864cec73add0cfaed0506aaa802b6ce`; native binary source is the SHA below. The latest native source is SHA `861ee477d926b5b5b709180ed404a9af3c7f8ae1`, based on merged ARM64 SHA `5601ed225aef1ecf8bb58f737b4142883d603bd7`, and the current macOS ARM64 package is [2026-09-15-02-16-01-aegisub-youtube-arm64](../artifacts/2026-09-15-02-16-01-aegisub-youtube-arm64). The original checkout and supplied subtitle originals remain unchanged. See the [guide](2026-09-15-15-13-04-youtube-guide.md) for usage and limitations.

## Published subtitle and device result

The corrected Korean track was uploaded through the authorized signed-in Aside session and published to [Adorena](https://www.youtube.com/watch?v=jOYcCNgJDn0). Desktop playback shows all three colored lines. The user confirmed that iPhone flicker was gone at **28–31 seconds after reopening the video**. This is device/segment evidence, not a guarantee for all iOS versions or the entire video.

The position-corrected variant did not resolve the user's iPhone flicker, and the user still observed flicker in the second single-outline variant. The initial grouped single-outline variant keeps one active caption per center/bottom region and combines simultaneous rows with line breaks. All **996 timing boundaries** retain the exact ordered original text/style spans, excluding inserted invisible separators. Karaoke color changes remain. Android fullscreen rows were already non-overlapping; the user accepts app-specific background/font differences.

- [Final files and hashes](../artifacts/2026-09-15-adrena/final-subtitles.json)
- [Boundary validation](../artifacts/2026-09-15-adrena/combined-lines-validation.json)
- [Desktop published result](../artifacts/2026-09-15-adrena/desktop-combined-29s.png)

The initial grouped YTT and imported editable ASS are stored beside the originals under `2026-09-15-아드레나-동시행묶음`. The imported ASS contains expanded color states, not the original authoring karaoke tags; keep the original ASS for timing edits. The posted YTT is the verified playback artifact.

## Restored shadow comparison

The original four effect layers were restored while retaining grouped rows, uploaded, and the user confirmed **no flicker in the iPhone app**. Shadow removal was therefore unnecessary for this case. The comparison expands 1,009 grouped blocks to 4,036 effect blocks while preserving rows, timing and colors. This restored-effects YTT is the currently published version. The user also reported normal mobile-browser playback. These observations do not generalize to every video or device. Row grouping was a separate treatment of this subtitle file, not an automatic feature applied to every app conversion.

## Resolution and tag-order experiments

Changing only PlayRes from 1920×1080 to 640×360 clamps the supplied positions to the lower-right corner. Resampling coordinates, font sizes, margins and border/shadow dimensions by one third produces **byte-identical YTT** to the original-resolution conversion. Thus 640×360 alone is not a fix for this file.

Moving `\pos` before or after the initial `\k` also produces byte-identical YTT in this converter: **614,468 bytes**, SHA-256 `d6b5477ffa8dec921227b1a2f96596a05b7f0b4d30e81c7df69d11e003b5e88f`. The original last row at 29 seconds already has `\pos` first. [Experiment evidence](../artifacts/2026-09-15-adrena/tag-order/2026-09-15-01-05-14-evidence.json).

## Native and packaged verification

- macOS package helper: **51 checks passed**, including 13 pinned upstream YTT goldens and 27 anchor/justification round trips. [Results](../artifacts/youtube-regression-final.json).
- The latest native macOS ARM64 package [2026-09-15-02-16-01-aegisub-youtube-arm64](../artifacts/2026-09-15-02-16-01-aegisub-youtube-arm64), for source SHA `861ee477d926b5b5b709180ed404a9af3c7f8ae1` based on merged ARM64 SHA `5601ed225aef1ecf8bb58f737b4142883d603bd7`, was directly launched with developer runtime variables removed and isolated settings. Under the Korean locale, GUI conversion and compatibility diagnostics were directly observed, including fade, transform and ytkt warnings in [mac-regex-diagnostics.png](../artifacts/2026-09-15-adrena/mac-regex-diagnostics.png). The sample converted 3 rows to 55 events and 22,904 bytes in **859 ms**. [QA record](../artifacts/2026-09-15-adrena/mac-package-qa.json). The prior 1,405 ms GUI observation and its [ready state](../artifacts/2026-09-15-adrena/mac-msvc-ready.jpg) remain historical; the **4-second video-QA** result was only the earlier **734 ms** observation from [the previous package](../artifacts/2026-09-15-01-00-46-aegisub-youtube-arm64), with its [earlier ready state](../artifacts/2026-09-15-adrena/mac-package-ready.jpg) and [video render](../artifacts/2026-09-15-adrena/mac-package-preview.jpg), and is not a latest-package result.
- Actual Windows 11 AMD64 helper: **16 smoke checks passed**, covering help, 13 goldens, Korean paths/import/source preservation, and rejected missing input. [Results](../artifacts/2026-09-15-adrena/windows-smoke-results.json).
- Actual Windows Chrome: the helper supplied the local YTT, received the matching response ACK, and displayed three colored rows. Its dedicated browser/profile was stopped and removed. [Status](../artifacts/2026-09-15-adrena/windows-player-status.txt).
- Windows portable native GUI verification is complete. On Windows 11 AMD64 in a Korean path containing spaces, ASS opening, YouTube conversion, compatibility diagnostics, and YTT/ASS/manifest export were verified: 3 rows → 55 events, 22,904 bytes, 1,129 ms, with matching export/manifest SHA-256. [QA record](../artifacts/2026-09-15-adrena/windows-native-qa.json). The initial dialog required manual resizing at this display setting. The full installer, optional codecs, and VC runtime requirements on a clean Windows installation remain unverified. CI passed the Windows native build and 354 C++ tests but failed the locked helper restore with NU1004. After the RuntimeIdentifier fix, a separate actual-Windows helper build and 16 checks passed. The existing wx-master dependency-patch failure remains; this is not a claim of a fully green CI matrix.

## Limits

macOS minimum version is 26.0; signing is ad-hoc, without Developer ID notarization. Clean-machine Gatekeeper acceptance is untested. ASS preview is an approximation; independent multiline justification can differ and is diagnosed. The external desktop player requires Chrome/Edge and an existing matching manual caption track. Response ACK establishes byte identity, while screenshots and device feedback establish the observed display.
