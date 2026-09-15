using System.Drawing;
using System.Runtime.InteropServices;
using YTSubConverter.Shared;

sealed class TextMeasurer : ITextMeasurer
{
    [DllImport("aegisub-text", CallingConvention = CallingConvention.Cdecl)]
    static extern void measure_text([MarshalAs(UnmanagedType.LPUTF8Str)] string text,
        [MarshalAs(UnmanagedType.LPUTF8Str)] string font, float size, int bold, int italic,
        out float width, out float height);

    public SizeF Measure(string text, string font, float size, bool bold, bool italic)
    {
        measure_text(text, font, size, bold ? 1 : 0, italic ? 1 : 0, out var w, out var h);
        return new SizeF(w, h);
    }
    public void Dispose() { }
}
