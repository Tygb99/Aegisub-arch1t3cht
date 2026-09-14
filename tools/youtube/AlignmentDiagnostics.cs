using YTSubConverter.Shared;
using YTSubConverter.Shared.Formats;
using YTSubConverter.Shared.Util;

static class AlignmentDiagnostics
{
    public const string PatchRevision = "c460cca9f5b37aa0e98e460007f7379df5732d05";

    public sealed record Issue(string code, string text, int line, double startMilliseconds,
        string anchor, int justification, bool multiline, string action, string message);

    public static Issue[] Inspect(SubtitleDocument document) => document.Lines
        .Select((line, index) => (line, index))
        .Where(item => item.line.Justification is { } value && value != Derived(item.line.AnchorPoint))
        .Select(item => new Issue("YTJU_VISUAL_ALIGNMENT", item.line.Text, item.index + 1,
            (item.line.Start - SubtitleDocument.TimeBase).TotalMilliseconds,
            item.line.AnchorPoint.ToString(), item.line.Justification!.Value,
            item.line.Text.Contains('\n'), "verify-result-ytt-in-player",
            "독립 정렬은 ytju 태그와 YTT에 보존됩니다. ASS 화면은 앵커 기준 정렬을 사용하므로 result.ytt를 실제 플레이어에서 확인하세요."))
        .ToArray();

    static int Derived(AnchorPoint anchor) => AnchorPointUtil.IsLeftAligned(anchor) ? 0
        : AnchorPointUtil.IsRightAligned(anchor) ? 1 : 2;
}
