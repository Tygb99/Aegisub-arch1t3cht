using System.Drawing;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using YTSubConverter.Shared;
using YTSubConverter.Shared.Formats.Ass;

sealed record OutputProfile(float Scale = 1, float OffsetX = 0, float OffsetY = 0, bool Mobile = false)
{
    public static OutputProfile Load(string? path)
    {
        var element = path == null ? null : XDocument.Load(path).Root?.Element("Output");
        float Number(string name, float fallback) => element?.Attribute(name) is { } attribute
            ? float.Parse(attribute.Value, CultureInfo.InvariantCulture) : fallback;
        var profile = new OutputProfile(Number("Scale", 1), Number("OffsetX", 0), Number("OffsetY", 0),
            (bool?)element?.Attribute("Mobile") ?? false);
        if (!float.IsFinite(profile.Scale) || profile.Scale is < 0.1f or > 4 ||
            !float.IsFinite(profile.OffsetX) || !float.IsFinite(profile.OffsetY))
            throw new ArgumentException("출력 배율은 0.1~4, 좌표 이동은 유한한 숫자여야 합니다.");
        return profile;
    }

    public string Prepare(string input, string directory)
    {
        if (!Mobile) return input;
        var lines = File.ReadAllLines(input);
        for (int i = 0; i < lines.Length; i++)
        {
            if (!lines[i].StartsWith("Dialogue:")) continue;
            var fields = lines[i].Split(',', 10);
            if (fields.Length != 10) throw new InvalidDataException("ASS 이벤트 형식이 올바르지 않습니다.");
            var text = new System.Text.StringBuilder();
            var drawing = false;
            foreach (var part in Regex.Split(fields[9], @"(\{[^}]*\})"))
            {
                if (part.StartsWith('{'))
                {
                    foreach (Match mode in Regex.Matches(part, @"\\p(\d+)\b"))
                        drawing = mode.Groups[1].Value.TrimStart('0').Length != 0;
                }
                else if (!drawing) text.Append(part);
            }
            fields[9] = text.ToString();
            lines[i] = string.Join(',', fields);
        }
        var path = Path.Combine(directory, "mobile-" + Guid.NewGuid().ToString("N") + ".ass");
        using var output = new StreamWriter(new FileStream(path, FileMode.CreateNew, FileAccess.Write));
        foreach (var line in lines) output.WriteLine(line);
        return path;
    }

    public void Apply(AssDocument document)
    {
        foreach (var line in document.Lines)
        {
            if (Mobile)
            {
                line.Position = null;
                line.AnchorPoint = AnchorPoint.BottomCenter;
                var text = line.Text;
                line.Sections.Clear();
                line.Sections.Add(new Section(text) { Font = "Roboto", ForeColor = Color.White,
                    BackColor = Color.FromArgb(192, 0, 0, 0), Scale = Scale });
            }
            else
            {
                foreach (var section in line.Sections) section.Scale *= Scale;
                if (line.Position is { } point && (OffsetX != 0 || OffsetY != 0))
                {
                    point = new PointF(point.X + OffsetX, point.Y + OffsetY);
                    if (point.X < 0 || point.X > document.VideoDimensions.Width || point.Y < 0 || point.Y > document.VideoDimensions.Height)
                        throw new ArgumentException("위치 이동 결과가 PlayRes 범위를 벗어납니다.");
                    line.Position = point;
                }
            }
        }
    }
}
