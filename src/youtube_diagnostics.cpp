#include "dialog_youtube.h"
#include "ass_dialogue.h"
#include "ass_file.h"
#include "ass_style.h"
#include "compat.h"
#include "include/aegisub/context.h"
#include <wx/listctrl.h>
#include <set>
#include <boost/regex.hpp>
#include <locale>
#include <algorithm>
#include <cctype>

void DialogYoutube::Diagnose() {
	issues->DeleteAllItems(); issue_ids.clear();
	const std::set<std::string> supported = {"b","i","u","fn","fs","c","1c","2c","3c","4c","1a","2a","3a","4a","alpha","pos","an","k","r","fad","fade","move","t","ytsub","ytsup","ytsur","ytruby","ytvert","ytdir","ytpack","ytshake","ytchroma","ytkt","ytju"};
	const std::set<std::string> fonts = {"roboto","arial","courier new","courier","nimbus mono l","cutive mono","times new roman","times","georgia","cambria","pt serif caption","deja vu sans mono","dejavu sans mono","lucida console","monaco","consolas","pt mono","comic sans ms","impact","handlee","monotype corsiva","urw chancery l","apple chancery","dancing script","carrois gothic sc"};
	auto ass_regex = [](char const *pattern) {
		boost::regex regex;
		regex.imbue(std::locale::classic());
		regex.assign(pattern);
		return regex;
	};
	auto groups = ass_regex(R"(\{([^}]*)\})"), tags = ass_regex(R"(\\(fn|r|[0-9]?[a-z]+))"), position = ass_regex(R"(\\pos\(\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)\s*\))");
	int width, height; c->ass->GetResolution(width, height);
	auto base = c->ass->GetStyle("Default");
	if (!base && !c->ass->Styles.empty()) base = &c->ass->Styles.front();
	int row = 0;
	std::vector<AssDialogue const*> active;
	for (auto const& line : c->ass->Events) {
		++row; if (line.Comment) continue;
		auto add = [&](wxString const& message) {
			auto index = issues->InsertItem(issues->GetItemCount(), wxString::Format("%d / %s", row, to_wx(line.Start.GetAssFormatted())));
			issues->SetItem(index, 1, message); issue_ids.push_back(line.Id);
		};
		auto style = c->ass->GetStyle(line.Style);
		if (style) {
			auto font = style->font;
			std::transform(font.begin(), font.end(), font.begin(), [](unsigned char ch) { return std::tolower(ch); });
			if (!fonts.count(font)) add("폰트 · " + to_wx(style->font) + " → Roboto 계열 대체 · 모든 환경");
			if (base && base->fontsize > 0) add(wxString::Format("크기 · 기준 %s %.1f 대비 %.1f%% · Android 크기 차이는 별도 확인", to_wx(base->name), base->fontsize, style->fontsize / base->fontsize * 100));
			if (style->primary.r + style->primary.g + style->primary.b < 160 && style->borderstyle != 3)
				add("색·배경 · 어두운 글자와 투명 배경은 모바일에서 읽기 어려울 수 있음 · 모바일");
		}
		auto const& text = line.Text.get();
		for (auto group = boost::sregex_iterator(text.begin(), text.end(), groups); group != boost::sregex_iterator(); ++group) {
			auto block = (*group)[1].str();
			for (auto tag = boost::sregex_iterator(block.begin(), block.end(), tags); tag != boost::sregex_iterator(); ++tag) {
				auto name = (*tag)[1].str();
				if (!supported.count(name)) add("\\" + to_wx(name) + " · 현재 변환기에서 무시됨 · YouTube 전체");
				if (name == "ytju") add("독립 정렬 · YTT 값은 보존되지만 ASS 근사 화면의 줄 정렬은 다를 수 있음 · 실제 플레이어 확인");
				if (name == "fad" || name == "fade") add("페이드 · 그림자·외곽선 색이 #222222가 아니면 잔상이 남을 수 있음 · YouTube 전체");
				if (name == "ytkt" || name == "ytshake" || name == "ytchroma" || name == "t") add("\\" + to_wx(name) + " · 이벤트 확장 및 파일 증가, 실기기 성능 확인 필요 · 모바일");
				if (name == "ytruby" || name == "ytvert" || name == "ytsub" || name == "ytsup") add("\\" + to_wx(name) + " · 데스크톱 전용 또는 모바일 대체 표현 · 모바일");
			}
		}
		boost::smatch match;
		if (boost::regex_search(text, match, position)) {
			try { double x = std::stod(match[1]), y = std::stod(match[2]);
				if (x < 0 || x > width || y < 0 || y > height) add("\\pos · PlayRes 밖 좌표, 실제 플레이어 표시 미검증 · 모든 환경");
			} catch (std::exception const&) { add("\\pos · 좌표 숫자를 해석할 수 없음 · 모든 환경"); }
		}
		if (line.End <= line.Start) add("시간 · 종료가 시작보다 늦어야 함 · 모든 환경");
		for (auto previous : active) if (line.Start < previous->End && previous->Start < line.End) {
			add("겹침 · 다른 행과 시간이 겹침 (실제 글자 충돌은 화면에서 확인) · 모든 환경"); break;
		}
		active.push_back(&line);
	}
}
