#include "dialog_youtube.h"
#include "ass_dialogue.h"
#include "ass_file.h"
#include "ass_style.h"
#include "compat.h"
#include "include/aegisub/context.h"
#include "selection_controller.h"
#include "text_selection_controller.h"
#include <wx/button.h>
#include <wx/choice.h>
#include <wx/clrpicker.h>
#include <wx/msgdlg.h>
#include <wx/panel.h>
#include <wx/sizer.h>
#include <wx/spinctrl.h>
#include <wx/stattext.h>
#include <wx/textctrl.h>
#include <wx/scrolwin.h>
#include <wx/sstream.h>
#include <wx/xml/xml.h>
#include <algorithm>

wxPanel *DialogYoutube::MakeEffects(wxWindow *parent) {
	auto panel = new wxScrolledWindow(parent); panel->SetScrollRate(0, 10);
	auto layout = new wxBoxSizer(wxVERTICAL);
	auto property = new wxChoice(panel, -1);
	for (auto label : {wxS("위치 (X, Y)"), wxS("정렬 (1~9)"), wxS("글자 크기"), wxS("글자색"), wxS("외곽선 두께"), wxS("그림자 거리"), wxS("페이드 (등장·퇴장 ms)"), wxS("크기·색 변형 구간 추가"), wxS("가라오케 효과"), wxS("커서 앞 음절 시간 (ms)"), wxS("YouTube 전용 효과")}) property->Append(label);
	property->SetSelection(0);
	layout->Add(property, 0, wxALL | wxEXPAND, 10);
	auto grid = new wxFlexGridSizer(4, 8, 8);
	auto number = [&](wxString const& label, int value, int maximum) {
		grid->Add(new wxStaticText(panel, -1, label), 0, wxALIGN_CENTER_VERTICAL);
		auto field = new wxSpinCtrl(panel, -1, "", wxDefaultPosition, wxSize(90, -1), wxSP_ARROW_KEYS, 0, maximum, value);
		grid->Add(field); return field;
	};
	int w, h; c->ass->GetResolution(w, h);
	auto first = number(wxS("X / 단일 값"), w / 2, 100000);
	auto second = number(wxS("Y / 퇴장 ms"), h * 9 / 10, 100000);
	auto start = number(wxS("변형 시작 ms"), 0, 3600000);
	auto end = number(wxS("변형 종료 ms"), 500, 3600000);
	grid->Add(new wxStaticText(panel, -1, wxS("가속도")), 0, wxALIGN_CENTER_VERTICAL);
	auto accel = new wxSpinCtrlDouble(panel, -1, "1", wxDefaultPosition, wxSize(90, -1), wxSP_ARROW_KEYS, 0.01, 100, 1, 0.1);
	grid->Add(accel);
	grid->Add(new wxStaticText(panel, -1, wxS("글자색 / 변형 끝색")), 0, wxALIGN_CENTER_VERTICAL);
	auto color = new wxColourPickerCtrl(panel, -1, *wxWHITE); grid->Add(color);
	layout->Add(grid, 0, wxALL, 10);
	auto kind = new wxChoice(panel, -1);
	for (auto label : {wxS("Fade"), wxS("Glitch"), wxS("Cursor"), wxS("흔들기 (ytshake)"), wxS("색 분리 (ytchroma)"), wxS("루비 (ytruby)"), wxS("세로쓰기 (ytvert9)")}) kind->Append(label);
	kind->SetSelection(0);
	layout->Add(kind, 0, wxALL | wxEXPAND, 10);
	auto cursor = new wxTextCtrl(panel, -1, "_");
	cursor->SetToolTip(wxS("Cursor 효과의 문자. 쉼표·괄호·중괄호는 사용할 수 없습니다."));
	layout->Add(cursor, 0, wxALL | wxEXPAND, 10);
	auto effect_help = new wxStaticText(panel, -1, wxS("Fade: 음절을 부드럽게 강조합니다. 예: {\\ytktFade}{\\k25}한{\\k25}글 · 파일이 커질 수 있습니다."));
	effect_help->Wrap(680); layout->Add(effect_help, 0, wxLEFT | wxRIGHT | wxEXPAND, 10);
	kind->Bind(wxEVT_CHOICE, [=](wxCommandEvent&) {
		const wxString examples[] = {
			wxS("Fade: 예 {\\ytktFade}{\\k25}한{\\k25}글 · 음절 강조, 파일 증가 가능"),
			wxS("Glitch: 예 {\\ytktGlitch}{\\k25}한{\\k25}글 · 임의 글자로 전환, 왼쪽 정렬 권장"),
			wxS("Cursor: 예 {\\ytkt(Cursor,_)}{\\k25}한{\\k25}글 · 현재 음절 뒤의 커서 문자"),
			wxS("흔들기: 예 {\\ytshake(20)} · X / 단일 값은 반경 px, 이벤트 수 증가"),
			wxS("색 분리: 예 {\\ytchroma} · 기본 20px, 등장·퇴장 270ms, 이벤트 수 증가"),
			wxS("루비: 예 {\\ytruby}[漢/かん] · 데스크톱 위첨자, 모바일은 괄호로 대체"),
			wxS("세로쓰기: 예 {\\ytvert9}세로 글 · 오른쪽부터 세로 열, 데스크톱 전용")
		};
		effect_help->SetLabel(examples[kind->GetSelection()]); effect_help->Wrap(680); panel->Layout();
	});
	auto explanation = new wxStaticText(panel, -1, wxS("선택한 속성만 변경합니다. 기존 태그 편집·스타일 편집·가라오케 시간 도구도 그대로 사용하세요.\n위치는 현재 PlayRes 범위 안에서 설정합니다. 화면 밖 좌표의 실제 플레이어 지원은 미검증입니다.\n변형은 행 시작 기준 ms이며 구간을 반복 추가할 수 있습니다.\n음절 시간은 텍스트 커서 앞에 삽입됩니다. ASS \\k 단위는 10ms입니다."));
	explanation->Wrap(680); layout->Add(explanation, 0, wxALL, 10);
	auto apply = new wxButton(panel, -1, wxS("변경 내용 확인 후 선택 행에 적용…"));
	layout->Add(apply, 0, wxALL, 10);
	panel->SetSizer(layout);
	apply->Bind(wxEVT_BUTTON, [=](wxCommandEvent&) {
		int w, h; c->ass->GetResolution(w, h);
		auto line = c->selectionController->GetActiveLine(); if (!line) return;
		auto rgb = color->GetColour();
		auto ass_color = wxString::Format("&H%02X%02X%02X&", rgb.Blue(), rgb.Green(), rgb.Red());
		wxString tag, name; int value = first->GetValue();
		if (property->GetSelection() == 4 || property->GetSelection() == 5) {
			auto original = c->ass->GetStyle(line->Style); if (!original) return;
			auto label = property->GetSelection() == 4 ? wxS("외곽선") : wxS("그림자");
			if (wxMessageBox(wxString::Format(wxS("선택 행 전용 스타일을 복제하고 %s 값을 %d로 설정합니다.\nYouTube는 스타일의 외곽선·그림자를 사용하며 두께는 동일하게 재현되지 않습니다.\n실행 취소할 수 있습니다."), label, value), wxS("스타일 변경 확인"), wxOK | wxCANCEL, this) != wxOK) return;
			auto copy = new AssStyle(*original);
			int suffix = 1;
			do { copy->name = original->name + " YouTube " + std::to_string(suffix++); } while (c->ass->GetStyle(copy->name));
			if (property->GetSelection() == 4) copy->outline_w = value; else copy->shadow_w = value;
			auto xml = to_wx(c->ass->GetScriptInfo("Aegisub Youtube Options"));
			wxStringInputStream input(xml); wxXmlDocument options;
			if (!xml.empty() && options.Load(input) && options.GetRoot()) {
				for (auto node = options.GetRoot()->GetChildren(); node; node = node->GetNext()) {
					wxXmlNode *name = nullptr;
					for (auto child = node->GetChildren(); child; child = child->GetNext())
						if (child->GetName() == "Name" && child->GetNodeContent() == to_wx(original->name)) name = child;
					if (!name) continue;
					auto cloned = new wxXmlNode(*node);
					for (auto child = cloned->GetChildren(); child; child = child->GetNext())
						if (child->GetName() == "Name" && child->GetChildren()) child->GetChildren()->SetContent(to_wx(copy->name));
					options.GetRoot()->AddChild(cloned);
					wxStringOutputStream output; options.Save(output, 0);
					xml = output.GetString(); xml.Replace("\n", ""); xml.Replace("\r", "");
					c->ass->SetScriptInfo("Aegisub Youtube Options", from_wx(xml)); break;
				}
			}
			copy->UpdateData(); c->ass->Styles.push_back(*copy); line->Style = copy->name;
			c->ass->Commit(wxS("YouTube 선택 행 스타일"), AssFile::COMMIT_STYLES | AssFile::COMMIT_DIAG_META | AssFile::COMMIT_SCRIPTINFO);
			return;
		}
		switch (property->GetSelection()) {
			case 0:
				if (value > w || second->GetValue() > h) { wxMessageBox(wxS("현재 PlayRes 범위 안의 좌표를 입력하세요."), wxS("위치"), wxOK, this); return; }
				name = "\\pos"; tag = wxString::Format("\\pos(%d,%d)", value, second->GetValue()); break;
			case 1: if (value < 1 || value > 9) return; name = "\\an"; tag = wxString::Format("\\an%d", value); break;
			case 2: if (value < 1) return; name = "\\fs"; tag = wxString::Format("\\fs%d", value); break;
			case 3: name = "\\c"; tag = "\\c" + ass_color; break;
			case 6: name = "\\fad"; tag = wxString::Format("\\fad(%d,%d)", value, second->GetValue()); break;
			case 7:
				if (start->GetValue() >= end->GetValue() || end->GetValue() > line->End - line->Start || value < 1) {
					wxMessageBox(wxS("변형 시작 < 종료 ≤ 행 길이, 크기 > 0이어야 합니다."), wxS("변형 구간"), wxOK, this); return;
				}
				tag = wxString::Format("\\t(%d,%d,%.2f,\\fs%d\\c%s)", start->GetValue(), end->GetValue(), accel->GetValue(), value, ass_color); break;
			case 8:
				name = "\\ytkt";
				if (kind->GetSelection() == 0) tag = "\\ytktFade";
				else if (kind->GetSelection() == 1) tag = "\\ytktGlitch";
				else {
					auto text = cursor->GetValue();
					if (text.empty() || text.find_first_of(",(){}\\\r\n") != wxString::npos) return;
					tag = "\\ytkt(Cursor," + text + ")";
				} break;
			case 9: tag = wxString::Format("\\k%d", (value + 5) / 10); break;
			case 10:
				switch (kind->GetSelection()) {
					case 3: name = "\\ytshake"; tag = wxString::Format("\\ytshake(%d)", value); break;
					case 4: name = "\\ytchroma"; tag = "\\ytchroma"; break;
					case 5: name = "\\ytruby"; tag = "\\ytruby"; break;
					case 6: name = "\\ytvert"; tag = "\\ytvert9"; break;
					default: return;
				} break;
			default: return;
		}
		if (wxMessageBox(wxS("행 ") + wxString::Format("%d", line->Row + 1) + wxS("에 적용: {") + tag + wxS("}\n실행 취소할 수 있습니다."), wxS("변경 확인"), wxOK | wxCANCEL, this) != wxOK) return;
		if (property->GetSelection() == 9) {
			auto text = line->Text.get();
			auto pos = std::min(text.size(), static_cast<size_t>(c->textSelectionController->GetInsertionPoint()));
			auto prefix = text.substr(0, pos);
			if (prefix.rfind('{') != std::string::npos && (prefix.rfind('}') == std::string::npos || prefix.rfind('{') > prefix.rfind('}'))) {
				wxMessageBox(wxS("태그 바깥의 음절 앞에 텍스트 커서를 놓으세요."), wxS("음절 시간"), wxOK, this); return;
			}
			text.insert(pos, "{" + from_wx(tag) + "}"); line->Text = text;
		} else {
			auto blocks = line->ParseTags();
			if (blocks.empty() || blocks.front()->GetType() != AssBlockType::OVERRIDE)
				blocks.insert(blocks.begin(), std::make_unique<AssDialogueBlockOverride>());
			auto block = static_cast<AssDialogueBlockOverride*>(blocks.front().get());
			if (!name.empty()) block->Tags.erase(std::remove_if(block->Tags.begin(), block->Tags.end(), [&](AssOverrideTag const& old) {
				return old.Name == from_wx(name) || (name == "\\pos" && old.Name == "\\move") || (name == "\\c" && old.Name == "\\1c");
			}), block->Tags.end());
			block->AddTag(from_wx(tag)); line->UpdateText(blocks);
		}
		c->ass->Commit(wxS("YouTube 선택 행 효과"), AssFile::COMMIT_DIAG_TEXT, -1, line);
	});
	return panel;
}
