using System.Drawing;
using YTSubConverter.Shared;

sealed class TextMeasurer : ITextMeasurer
{
    Graphics? graphics;
    Font? lastFont;

    public TextMeasurer()
    {
        if (!System.OperatingSystem.IsWindowsVersionAtLeast(6, 1))
            throw new PlatformNotSupportedException("Windows 텍스트 측정에는 Windows 7 이상이 필요합니다.");
        graphics = Graphics.FromHwnd(IntPtr.Zero);
    }

    public SizeF Measure(string text, string font, float size, bool bold, bool italic)
    {
        if (!System.OperatingSystem.IsWindowsVersionAtLeast(6, 1))
            throw new PlatformNotSupportedException("Windows 텍스트 측정에는 Windows 7 이상이 필요합니다.");
        ObjectDisposedException.ThrowIf(graphics == null, this);
        if (lastFont == null || lastFont.Name != font || lastFont.Size != size ||
            lastFont.Bold != bold || lastFont.Italic != italic)
        {
            lastFont?.Dispose();
            var style = FontStyle.Regular;
            if (bold) style |= FontStyle.Bold;
            if (italic) style |= FontStyle.Italic;
            lastFont = new Font(font, size, style);
        }

        var result = graphics.MeasureString(text, lastFont, new PointF(), StringFormat.GenericTypographic);
        return new SizeF(result.Width * 0.97f, result.Height);
    }

    public void Dispose()
    {
        if (System.OperatingSystem.IsWindowsVersionAtLeast(6, 1))
        {
            graphics?.Dispose();
            lastFont?.Dispose();
        }
        graphics = null;
        lastFont = null;
    }
}
