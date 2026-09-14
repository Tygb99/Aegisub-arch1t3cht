#import <AppKit/AppKit.h>

void measure_text(const char *text, const char *name, float size, int bold, int italic,
                  float *width, float *height) {
    @autoreleasepool {
        NSFont *font = [NSFont fontWithName:@(name) size:size] ?: [NSFont systemFontOfSize:size];
        NSFontTraitMask traits = (bold ? NSBoldFontMask : 0) | (italic ? NSItalicFontMask : 0);
        font = [[NSFontManager sharedFontManager] convertFont:font toHaveTrait:traits];
        NSAttributedString *string = [[NSAttributedString alloc] initWithString:@(text)
            attributes:@{NSFontAttributeName: font}];
        NSRect rect = [string boundingRectWithSize:NSMakeSize(9999, 9999)
            options:NSStringDrawingUsesLineFragmentOrigin];
        *width = rect.size.width;
        *height = rect.size.height;
    }
}
