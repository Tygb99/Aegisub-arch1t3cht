#import <Cocoa/Cocoa.h>
#import <wx/wx.h>
#import <wx/stc/stc.h>

#include <functional>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

namespace osx { namespace ime { void inject(wxStyledTextCtrl *ctrl); } }

class IMETestApp : public wxApp {
public:
    bool OnInit() override { SetExitOnFrameDelete(false); return true; }
};
wxIMPLEMENT_APP_NO_MAIN(IMETestApp);

namespace {
void require(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}

std::string range_string(NSRange range) {
    return "{" + (range.location == NSNotFound ? "NSNotFound" : std::to_string(range.location))
        + "," + std::to_string(range.length) + "}";
}

void expect_range(NSRange actual, NSRange expected) {
    require(NSEqualRanges(actual, expected), "expected UTF16=" + range_string(expected)
        + " actual=" + range_string(actual));
}

struct Editor {
    wxFrame *window;
    wxStyledTextCtrl *ctrl;
    NSView<NSTextInputClient> *client;

    explicit Editor(bool prewarm_context = false) {
        window = new wxFrame(nullptr, wxID_ANY, "Scintilla IME bridge test", wxDefaultPosition, wxSize(480, 200));
        ctrl = new wxStyledTextCtrl(window, wxID_ANY, wxDefaultPosition, wxSize(460, 180));
        ctrl->SetCodePage(wxSTC_CP_UTF8);
        client = (NSView<NSTextInputClient> *)ctrl->GetHandle();
        if (prewarm_context) (void)[client inputContext];
        osx::ime::inject(ctrl);
    }

    ~Editor() { delete window; }

    void text(NSString *value) {
        ctrl->SetText(wxString::FromUTF8([value UTF8String]));
        ctrl->SetSelection(ctrl->GetLength(), ctrl->GetLength());
        ctrl->EmptyUndoBuffer();
    }

    void expect_text(NSString *expected) {
        std::string actual = ctrl->GetText().ToStdString(wxConvUTF8);
        require(actual == [expected UTF8String], "expected text=" + std::string([expected UTF8String])
            + " actual=" + actual);
    }

    void mark(NSString *value, NSRange replacement = NSMakeRange(NSNotFound, 0)) {
        [client setMarkedText:value selectedRange:NSMakeRange([value length], 0) replacementRange:replacement];
    }

    void commit(NSString *value, NSRange replacement = NSMakeRange(NSNotFound, 0)) {
        [client insertText:value replacementRange:replacement];
    }
};

int failures = 0;
int cases = 0;
void test(const char *name, std::function<void()> body) {
    ++cases;
    @try {
        try {
            body();
            std::cout << "PASS " << name << std::endl;
        } catch (const std::exception &error) {
            ++failures;
            std::cout << "FAIL " << name << ": " << error.what() << std::endl;
        }
    } @catch (NSException *error) {
        ++failures;
        std::cout << "FAIL " << name << ": Objective-C " << [[error description] UTF8String] << std::endl;
    }
}
}

int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "--help") {
        std::cout << "Usage: scintilla_ime\nDirect NSTextInputClient regression tests on a real, hidden wxStyledTextCtrl.\n";
        return 0;
    }
    if (argc != 1) { std::cerr << "Unexpected argument; use --help\n"; return 2; }
    @autoreleasepool {
        if (!wxEntryStart(argc, argv) || !wxTheApp->CallOnInit()) {
            std::cerr << "Cannot initialize wxWidgets Cocoa test application\n";
            return 2;
        }
        std::cout << "Direct bridge calls; hidden test windows; no physical keyboard/IME input or Aegisub UI.\n";

        test("selectedRange uses UTF16 after Korean and emoji", [] {
            Editor e;
            e.text(@"한😀바끝");
            e.ctrl->SetSelection(7, 10);
            expect_range([e.client selectedRange], NSMakeRange(3, 1));
        });

        test("markedRange uses UTF16 after Korean and emoji", [] {
            Editor e;
            e.text(@"한😀");
            e.mark(@"바");
            e.expect_text(@"한😀바");
            expect_range([e.client markedRange], NSMakeRange(3, 1));
        });

        test("marked selection uses UTF16 including surrogate pairs", [] {
            Editor e;
            e.text(@"한😀");
            [e.client setMarkedText:@"밥😀" selectedRange:NSMakeRange(1, 2)
                replacementRange:NSMakeRange(NSNotFound, 0)];
            expect_range([e.client selectedRange], NSMakeRange(4, 2));
        });

        test("replacementRange reopens a syllable to add batchim", [] {
            Editor e;
            e.text(@"한😀바");
            e.mark(@"밥", NSMakeRange(3, 1));
            e.expect_text(@"한😀밥");
            expect_range([e.client markedRange], NSMakeRange(3, 1));
        });

        test("marked syllable updates preserve prefix and suffix", [] {
            Editor e;
            e.text(@"한😀끝");
            e.ctrl->SetSelection(7, 7);
            e.mark(@"ㅂ");
            e.mark(@"바");
            e.mark(@"밥", NSMakeRange(3, 1));
            e.commit(@"밥");
            e.expect_text(@"한😀밥끝");
            require(![e.client hasMarkedText], "Commit left marked text active");
        });

        test("insertText honors document replacementRange", [] {
            Editor e;
            e.text(@"한😀바끝");
            e.commit(@"밥", NSMakeRange(3, 1));
            e.expect_text(@"한😀밥끝");
        });

        test("attributedSubstring returns UTF16 context and actualRange", [] {
            Editor e;
            e.text(@"한😀밥");
            NSRange actual = NSMakeRange(NSNotFound, 0);
            NSAttributedString *value = [e.client attributedSubstringForProposedRange:NSMakeRange(1, 3) actualRange:&actual];
            require(value != nil, "Context substring is nil");
            require([[value string] isEqualToString:@"😀밥"], "Wrong context substring");
            expect_range(actual, NSMakeRange(1, 3));
        });

        test("candidate rectangle uses UTF16 range and screen coordinates", [] {
            Editor e;
            e.text(@"한😀밥끝");
            NSRange actual = NSMakeRange(NSNotFound, 0);
            NSRect rect = [e.client firstRectForCharacterRange:NSMakeRange(3, 1) actualRange:&actual];
            expect_range(actual, NSMakeRange(3, 1));
            auto start = e.ctrl->PointFromPosition(7);
            auto end = e.ctrl->PointFromPosition(10);
            NSRect expected = NSMakeRect(start.x, start.y, end.x - start.x, e.ctrl->TextHeight(0));
            expected = [e.client convertRect:expected toView:nil];
            expected = [[e.client window] convertRectToScreen:expected];
            require(std::abs(rect.origin.x - expected.origin.x) < 1
                && std::abs(rect.origin.y - expected.origin.y) < 1
                && std::abs(rect.size.width - expected.size.width) < 1
                && std::abs(rect.size.height - expected.size.height) < 1, "Wrong candidate screen rectangle");
        });

        test("characterIndexForPoint returns UTF16 from screen coordinates", [] {
            Editor e;
            e.text(@"한😀밥끝");
            auto point = e.ctrl->PointFromPosition(7);
            NSPoint screen = [e.client convertPoint:NSMakePoint(point.x + 1, point.y + 1) toView:nil];
            screen = [[e.client window] convertPointToScreen:screen];
            auto actual = [e.client characterIndexForPoint:screen];
            require(actual == 3, "expected UTF16 index=3 actual=" + std::to_string(actual));
        });

        test("composition commit is one undoable edit", [] {
            Editor e;
            e.text(@"한😀");
            e.mark(@"ㅂ");
            e.mark(@"바");
            e.mark(@"밥");
            e.commit(@"밥");
            e.expect_text(@"한😀밥");
            require(e.ctrl->GetUndoCollection() && e.ctrl->CanUndo(), "Undo was not restored");
            expect_range([e.client markedRange], NSMakeRange(NSNotFound, 0));
            e.ctrl->Undo();
            e.expect_text(@"한😀");
            require(!e.ctrl->CanUndo(), "Composition created multiple undo steps");
            e.ctrl->Redo();
            e.expect_text(@"한😀밥");
        });

        test("replacement composition undo restores original syllable", [] {
            Editor e;
            e.text(@"한😀바");
            e.mark(@"밥", NSMakeRange(3, 1));
            e.commit(@"밥");
            e.expect_text(@"한😀밥");
            e.ctrl->Undo();
            e.expect_text(@"한😀바");
            e.ctrl->Redo();
            e.expect_text(@"한😀밥");
        });

        test("partial marked replacement preserves the rest and undoes once", [] {
            Editor e;
            e.text(@"한😀");
            e.mark(@"바다");
            e.mark(@"밥", NSMakeRange(3, 1));
            e.expect_text(@"한😀밥다");
            expect_range([e.client markedRange], NSMakeRange(3, 2));
            e.commit(@"밥다");
            e.expect_text(@"한😀밥다");
            e.ctrl->Undo();
            e.expect_text(@"한😀");
            require(!e.ctrl->CanUndo(), "Partial update created multiple undo steps");
            e.ctrl->Redo();
            e.expect_text(@"한😀밥다");
        });

        test("implicit selected text replacement restores selection text on undo", [] {
            Editor e;
            e.text(@"한😀바끝");
            e.ctrl->SetSelection(7, 10);
            e.mark(@"밥");
            e.commit(@"밥");
            e.expect_text(@"한😀밥끝");
            e.ctrl->Undo();
            e.expect_text(@"한😀바끝");
        });

        test("empty marked string ends composition and preserves deletion undo", [] {
            Editor e;
            e.text(@"한😀바끝");
            e.mark(@"밥", NSMakeRange(3, 1));
            e.mark(@"");
            e.expect_text(@"한😀끝");
            require(![e.client hasMarkedText] && e.ctrl->GetUndoCollection(), "Empty mark left composition active");
            expect_range([e.client markedRange], NSMakeRange(NSNotFound, 0));
            e.ctrl->Undo();
            e.expect_text(@"한😀바끝");
        });

        test("empty insertText deletes explicit replacement range", [] {
            Editor e;
            e.text(@"한😀바끝");
            e.commit(@"", NSMakeRange(3, 1));
            e.expect_text(@"한😀끝");
            e.ctrl->Undo();
            e.expect_text(@"한😀바끝");
        });

        test("commit honors partial replacement inside an active mark", [] {
            Editor e;
            e.text(@"한😀끝");
            e.ctrl->SetSelection(7, 7);
            e.mark(@"바다");
            e.commit(@"밥", NSMakeRange(3, 1));
            e.expect_text(@"한😀밥다끝");
            require(![e.client hasMarkedText], "Partial commit left marked text active");
            e.ctrl->Undo();
            e.expect_text(@"한😀끝");
        });

        test("composition preserves disabled undo collection", [] {
            Editor e;
            e.text(@"한😀");
            e.ctrl->SetUndoCollection(false);
            e.mark(@"밥");
            e.commit(@"밥");
            e.expect_text(@"한😀밥");
            require(!e.ctrl->GetUndoCollection() && !e.ctrl->CanUndo(), "Commit enabled undo unexpectedly");
            e.mark(@"끝");
            [e.client unmarkText];
            e.expect_text(@"한😀밥끝");
            require(!e.ctrl->GetUndoCollection() && !e.ctrl->CanUndo(), "Unmark enabled undo unexpectedly");
        });

        test("unmarkText retains composition and restores undo", [] {
            Editor e;
            e.text(@"한😀");
            e.mark(@"밥");
            [e.client unmarkText];
            e.expect_text(@"한😀밥");
            require(![e.client hasMarkedText] && e.ctrl->GetUndoCollection(), "Unmark left composition state active");
            e.ctrl->Undo();
            e.expect_text(@"한😀");
        });

        for (bool prewarm : {false, true}) {
            test(prewarm ? "preexisting inputContext and first responder" : "fresh inputContext and first responder", [prewarm] {
                Editor e(prewarm);
                NSWindow *window = [e.client window];
                require([window makeFirstResponder:e.client] && [window firstResponder] == e.client,
                    "Hidden window could not assign actual first responder");
                NSTextInputContext *context = [e.client inputContext];
                require(context != nil && [context client] == e.client, "Input context has no matching client");
                NSTextInputContext *current = [NSTextInputContext currentInputContext];
                NSString *source = [context selectedKeyboardInputSource];
                std::cout << "CONTEXT prewarm=" << prewarm << " first_responder=1 input_context=1 key_window="
                    << bool([window isKeyWindow]) << " app_active=" << bool([NSApp isActive])
                    << " context_is_current=" << bool(current == context)
                    << " current_client_matches=" << bool(current && [current client] == e.client)
                    << " input_source=" << (source ? [source UTF8String] : "nil") << " physical_ime_test=0\n";
                for (NSString *prefix : {@"", @" "}) {
                    e.text(prefix);
                    e.mark(@"ㅎ");
                    e.mark(@"하");
                    e.mark(@"한");
                    e.commit(@"한");
                    e.mark(@"ㄱ");
                    e.mark(@"그");
                    e.mark(@"글");
                    e.commit(@"글");
                    e.expect_text([prefix stringByAppendingString:@"한글"]);
                    std::cout << "CONTEXT word=한글 prefix_utf16=" << [prefix length] << " PASS\n";
                }
            });
        }

        wxTheApp->OnExit();
        wxEntryCleanup();
    }
    std::cout << "RESULT cases=" << cases << " failures=" << failures << std::endl;
    return failures ? 1 : 0;
}
