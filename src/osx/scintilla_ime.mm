// Copyright (c) 2014, Thomas Goyne <plorkyeran@aegisub.org>
//
// Permission to use, copy, modify, and distribute this software for any
// purpose with or without fee is hereby granted, provided that the above
// copyright notice and this permission notice appear in all copies.
//
// THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
// WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
// MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
// ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
// WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
// ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
// OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
//
// Aegisub Project http://www.aegisub.org/

#import <objc/runtime.h>
#import <wx/osx/private.h>
#import <wx/stc/stc.h>

// from src/osx/cocoa/window.mm
@interface wxNSView : NSView <NSTextInputClient> {
    BOOL _hasToolTip;
    NSTrackingRectTag _lastToolTipTrackTag;
    id _lastToolTipOwner;
    void *_lastUserData;
}
@end

@interface IMEState : NSObject
@property (nonatomic) NSRange markedRange;
@property (nonatomic) bool undoActive;
@property (nonatomic, copy) NSString *originalText;
@end

@implementation IMEState
- (id)init {
    self = [super init];
    self.markedRange = NSMakeRange(NSNotFound, 0);
    self.undoActive = false;
    return self;
}
- (void)dealloc {
    [_originalText release];
    [super dealloc];
}
@end

@interface ScintillaNSView : wxNSView <NSTextInputClient>
@property (nonatomic, readonly) wxStyledTextCtrl *stc;
@property (nonatomic, readonly) IMEState *state;
@end

@implementation ScintillaNSView
- (Class)superclass {
    return [wxNSView superclass];
}

- (wxStyledTextCtrl *)stc {
    return static_cast<wxStyledTextCtrl *>(wxWidgetImpl::FindFromWXWidget(self)->GetWXPeer());
}

- (IMEState *)state {
    return objc_getAssociatedObject(self, [IMEState class]);
}

- (NSString *)text {
    return [NSString stringWithUTF8String:self.stc->GetTextRaw().data()];
}

// Cocoa ranges use UTF-16 code units; Scintilla positions use UTF-8 bytes.
- (NSRange)utf16Range:(NSRange)range {
    if (range.location == NSNotFound) return range;
    auto stc = self.stc;
    auto prefix = stc->GetTextRange(0, range.location);
    auto selected = stc->GetTextRange(range.location, NSMaxRange(range));
    return NSMakeRange([[NSString stringWithUTF8String:prefix.utf8_str().data()] length],
                       [[NSString stringWithUTF8String:selected.utf8_str().data()] length]);
}

- (NSRange)utf8Range:(NSRange)range {
    if (range.location == NSNotFound) return range;
    auto text = self.text;
    range.location = std::min(range.location, text.length);
    range.length = std::min(range.length, text.length - range.location);
    return NSMakeRange([[text substringToIndex:range.location] lengthOfBytesUsingEncoding:NSUTF8StringEncoding],
                       [[text substringWithRange:range] lengthOfBytesUsingEncoding:NSUTF8StringEncoding]);
}

- (void)invalidate {
    if (self.state.originalText) {
        self.stc->SetUndoCollection(self.state.undoActive);
        self.state.originalText = nil;
    }
    self.state.markedRange = NSMakeRange(NSNotFound, 0);
    [self.inputContext discardMarkedText];
}

- (void)restoreComposition {
    auto state = self.state;
    auto stc = self.stc;
    auto pos = state.markedRange.location;
    stc->DeleteRange(pos, state.markedRange.length);
    stc->SetSelection(pos, pos);
    auto text = [state.originalText UTF8String];
    auto length = strlen(text);
    stc->AddTextRaw(text, length);
    stc->SetSelection(pos, pos + length);
    stc->SetUndoCollection(state.undoActive);
    state.markedRange = NSMakeRange(NSNotFound, 0);
    state.originalText = nil;
}

#pragma mark - NSTextInputClient

- (NSAttributedString *)attributedSubstringForProposedRange:(NSRange)aRange
                                                actualRange:(NSRangePointer)actualRange
{
    auto text = self.text;
    if (aRange.location == NSNotFound || aRange.location > text.length) return nil;
    aRange.length = std::min(aRange.length, text.length - aRange.location);
    if (actualRange) *actualRange = aRange;
    return [[[NSAttributedString alloc] initWithString:[text substringWithRange:aRange]] autorelease];
}

- (NSUInteger)characterIndexForPoint:(NSPoint)point {
    point = [self.window convertPointFromScreen:point];
    point = [self convertPoint:point fromView:nil];
    auto pos = self.stc->PositionFromPoint(wxPoint(point.x, point.y));
    return pos < 0 ? NSNotFound : [self utf16Range:NSMakeRange(pos, 0)].location;
}

- (BOOL)drawsVerticallyForCharacterAtIndex:(NSUInteger)charIndex {
    return NO;
}

- (NSRect)firstRectForCharacterRange:(NSRange)range
                         actualRange:(NSRangePointer)actualRange
{
    auto stc = self.stc;
    range = [self utf8Range:range];
    if (range.location == NSNotFound)
        range = NSMakeRange(stc->GetCurrentPos(), 0);
    int line = stc->LineFromPosition(range.location);
    int height = stc->TextHeight(line);
    auto pt = stc->PointFromPosition(range.location);

    int width = 0;
    if (range.length > 0) {
        // If the end of the range is on the next line, the range should be
        // truncated to the current line and actualRange should be set to the
        // truncated range
        int end_line = stc->LineFromPosition(range.location + range.length);
        if (end_line > line) {
            range.length = stc->PositionFromLine(line + 1) - 1 - range.location;
        }

        auto end_pt = stc->PointFromPosition(range.location + range.length);
        width = end_pt.x - pt.x;
    }

    if (actualRange) *actualRange = [self utf16Range:range];

    auto rect = NSMakeRect(pt.x, pt.y, width, height);
    rect = [self convertRect:rect toView:nil];
    return [self.window convertRectToScreen:rect];
}

- (BOOL)hasMarkedText {
    return self.state.markedRange.length > 0;
}

- (void)insertText:(id)str replacementRange:(NSRange)replacementRange {
    bool composing = self.state.originalText != nil;
    if (composing && replacementRange.location != NSNotFound) {
        [self setMarkedText:str selectedRange:NSMakeRange([str length], 0)
            replacementRange:replacementRange];
        int pos = self.stc->GetCurrentPos();
        [self unmarkText];
        self.stc->SetSelection(pos, pos);
        return;
    }
    if (composing)
        [self restoreComposition];
    else if (replacementRange.location != NSNotFound) {
        auto range = [self utf8Range:replacementRange];
        self.stc->SetSelection(range.location, NSMaxRange(range));
    }
    self.stc->BeginUndoAction();
    if ([str length] == 0)
        self.stc->ReplaceSelection("");
    else
        [super insertText:str replacementRange:NSMakeRange(NSNotFound, 0)];
    self.stc->EndUndoAction();
}

- (NSRange)markedRange {
    return [self utf16Range:self.state.markedRange];
}

- (NSRange)selectedRange {
    long from = 0, to = 0;
    self.stc->GetSelection(&from, &to);
    return [self utf16Range:NSMakeRange(from, to - from)];
}

- (void)setMarkedText:(id)str
        selectedRange:(NSRange)range
     replacementRange:(NSRange)replacementRange
{
    if ([str isKindOfClass:[NSAttributedString class]])
        str = [str string];

    auto stc = self.stc;
    auto state = self.state;

    NSRange target = replacementRange.location != NSNotFound
        ? [self utf8Range:replacementRange]
        : state.originalText ? state.markedRange : [self utf8Range:self.selectedRange];
    if (state.originalText && (target.location < state.markedRange.location ||
                              NSMaxRange(target) > NSMaxRange(state.markedRange)))
        [self unmarkText];
    if (!state.originalText) {
        auto original = stc->GetTextRange(target.location, NSMaxRange(target));
        state.originalText = [NSString stringWithUTF8String:original.utf8_str().data()];
        state.markedRange = target;
        state.undoActive = stc->GetUndoCollection();
        if (state.undoActive)
            stc->SetUndoCollection(false);
    }
    auto marked = state.markedRange;
    auto pos = target.location;
    stc->DeleteRange(pos, target.length);
    stc->SetSelection(pos, pos);

    auto utf8 = [str UTF8String];
    auto utf8len = strlen(utf8);
    stc->AddTextRaw(utf8, utf8len);

    state.markedRange = NSMakeRange(marked.location, marked.length - target.length + utf8len);

    stc->SetIndicatorCurrent(1);
    stc->IndicatorFillRange(pos, utf8len);

    // Re-enable undo if we got a zero-length string as that means we're done
    if (!state.markedRange.length)
        [self unmarkText];
    else {
        int start = pos;
        // Range is in utf-16 code units
        if (range.location > 0)
            start += [[str substringToIndex:range.location] lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
        int length = [[str substringWithRange:range] lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
        stc->SetSelection(start, start + length);
    }
}

- (void)unmarkText {
    auto state = self.state;
    if (state.originalText) {
        auto marked = self.stc->GetTextRange(state.markedRange.location, NSMaxRange(state.markedRange));
        [self restoreComposition];
        self.stc->BeginUndoAction();
        self.stc->ReplaceSelection(marked);
        self.stc->EndUndoAction();
    }
}

- (NSArray *)validAttributesForMarkedText {
    return @[];
}
@end

namespace osx { namespace ime {
void inject(wxStyledTextCtrl *ctrl) {
    id view = (id)ctrl->GetHandle();
    object_setClass(view, [ScintillaNSView class]);

    auto state = [IMEState new];
    objc_setAssociatedObject(view, [IMEState class], state,
                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    [state release];
}

void invalidate(wxStyledTextCtrl *ctrl) {
    [(ScintillaNSView *)ctrl->GetHandle() invalidate];
}

bool process_key_event(wxStyledTextCtrl *ctrl, wxKeyEvent &evt) {
    if (evt.GetModifiers() != 0) return false;
    if (evt.GetKeyCode() != WXK_RETURN && evt.GetKeyCode() != WXK_TAB) return false;
    if (![(ScintillaNSView *)ctrl->GetHandle() hasMarkedText]) return false;

    evt.Skip();
    return true;
}

} }
