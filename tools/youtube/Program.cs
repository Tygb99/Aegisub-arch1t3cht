using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using System.Xml;
using System.Xml.Serialization;
using YTSubConverter.Shared;
using YTSubConverter.Shared.Formats;
using YTSubConverter.Shared.Formats.Ass;

CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
try
{
    if (args.Length == 1 && args[0] == "--help")
    {
        Console.WriteLine("aegisub-youtube preview INPUT.ass OUTPUT_DIRECTORY [STYLE_OPTIONS.xml]\n" +
            "aegisub-youtube import INPUT.ytt OUTPUT.ass\n" +
            "aegisub-youtube player VIDEO_URL RESULT.ytt LANGUAGE SESSION_DIRECTORY");
        return 0;
    }
    if (args.Length == 5 && args[0] == "player")
    {
        await PlayerPreview.Run(args[1..]);
        return 0;
    }
    if (args.Length < 3 || args.Length > 4)
        throw new ArgumentException("사용법은 --help로 확인하세요.");
    if (Path.GetFullPath(args[1]) == Path.GetFullPath(args[2]))
        throw new ArgumentException("원본과 출력 경로가 같을 수 없습니다.");
    if (args[0] == "import")
    {
        if (File.Exists(args[2])) throw new IOException("출력 파일이 이미 존재합니다.");
        var temporary = args[2] + "." + Guid.NewGuid().ToString("N") + ".ass";
        try
        {
            var imported = SubtitleDocument.Load(args[1]);
            SubtitleDocument.Convert(imported, ".ass", false).Save(temporary);
            File.Move(temporary, args[2], false);
            var importIssues = AlignmentDiagnostics.Inspect(imported);
            if (importIssues.Length > 0)
                Console.Error.WriteLine(JsonSerializer.Serialize(new {
                    code = "YTJU_VISUAL_ALIGNMENT", count = importIssues.Length,
                    message = "독립 정렬값을 ASS에 보존했습니다. ASS 근사 화면의 정렬은 실제 YTT와 다를 수 있습니다.",
                    action = "verify-result-ytt-in-player"
                }));
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
        return 0;
    }
    if (args[0] != "preview") throw new ArgumentException("알 수 없는 명령입니다.");
    var watch = Stopwatch.StartNew();
    List<AssStyleOptions> options = [];
    if (args.Length == 4)
    {
        using var reader = XmlReader.Create(args[3], new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit });
        options = ((AssStyleOptionsList?)new XmlSerializer(typeof(AssStyleOptionsList)).Deserialize(reader))?.Options
            ?? throw new InvalidDataException("스타일 설정 XML이 올바르지 않습니다.");
    }
    Directory.CreateDirectory(args[2]);
    foreach (var name in new[] { "result.ytt", "preview.visual.ass", "compatible.srt", "source.ass", "manifest.json" })
        if (File.Exists(Path.Combine(args[2], name))) throw new IOException("출력 파일이 이미 존재합니다: " + name);
    var profile = OutputProfile.Load(args.Length == 4 ? args[3] : null);
    var prepared = profile.Prepare(args[1], args[2]);
    AssDocument source;
    try { source = new AssDocument(prepared, profile.Mobile ? [] : options); }
    finally { if (prepared != args[1]) File.Delete(prepared); }
    profile.Apply(source);
    var inputEvents = File.ReadLines(args[1]).Count(line => line.StartsWith("Dialogue:"));
    var yttPath = Path.Combine(args[2], "result.ytt");
    SubtitleDocument.Convert(source, ".ytt", false).Save(yttPath);
    using var measurer = new TextMeasurer();
    var visualSource = SubtitleDocument.Load(yttPath);
    var visualDiagnostics = AlignmentDiagnostics.Inspect(visualSource);
    SubtitleDocument.Convert(visualSource, ".ass", true, measurer)
        .Save(Path.Combine(args[2], "preview.visual.ass"));
    SubtitleDocument.Convert(new AssDocument(args[1]), ".srt", false)
        .Save(Path.Combine(args[2], "compatible.srt"));
    File.Copy(args[1], Path.Combine(args[2], "source.ass"), true);
    File.WriteAllText(Path.Combine(args[2], "manifest.json"), JsonSerializer.Serialize(new {
        engine = "b186a40bc21e58a8c9651cf616cbb5e80425dfc6",
        enginePatch = AlignmentDiagnostics.PatchRevision, assAlignmentTag = "ytju",
        visualDiagnostics, visualIndependentAlignmentPreserved = visualDiagnostics.Length == 0,
        inputSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[1]))),
        optionsSha256 = args.Length == 4 ? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[3]))) : "",
        yttSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(yttPath))),
        elapsedMilliseconds = watch.ElapsedMilliseconds, bytes = new FileInfo(yttPath).Length,
        inputEvents, expandedEvents = source.Lines.Count,
        eventExpansionRatio = inputEvents == 0 ? 0 : (double)source.Lines.Count / inputEvents,
        eventsPerSecond = source.Lines.Count == 0 ? 0 : source.Lines.Count / Math.Max(0.001,
            (source.Lines.Max(line => line.End) - source.Lines.Min(line => line.Start)).TotalSeconds),
        eventDensity = (source.Lines.Count == 0 ? 0 : source.Lines.Count / Math.Max(0.001,
            (source.Lines.Max(line => line.End) - source.Lines.Min(line => line.Start)).TotalSeconds)).ToString("F2"),
        profile, visualApproximation = true
    }));
    return 0;
}
catch (Exception error)
{
    Console.Error.WriteLine(error.Message);
    return 1;
}
