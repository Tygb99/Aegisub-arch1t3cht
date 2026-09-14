using System;

namespace YTSubConverter.Shared.Formats.Ass.Tags
{
    internal class AssJustificationTagHandler : AssTagHandlerBase
    {
        public override string Tag => "ytju";

        public override bool AffectsWholeLine => true;

        public override void Handle(AssTagContext context, string arg)
        {
            if (!TryParseInt(arg, out int justification) || justification < 0 || justification > 2)
                throw new ArgumentException("\\ytju 값은 0(왼쪽), 1(오른쪽), 2(가운데)여야 합니다.");

            context.Line.Justification = justification;
        }
    }
}
