#include "dialog_youtube.h"
#include "ass_file.h"
#include "ass_style.h"
#include "compat.h"
#include "include/aegisub/context.h"
#include <wx/button.h>
#include <wx/checkbox.h>
#include <wx/choice.h>
#include <wx/panel.h>
#include <wx/sizer.h>
#include <wx/stattext.h>
#include <wx/textctrl.h>
#include <wx/sstream.h>
#include <wx/xml/xml.h>
#include <wx/spinctrl.h>
#include <wx/scrolwin.h>

namespace {
wxXmlDocument Options(AssFile *ass) {
	wxXmlDocument doc;
	auto xml = to_wx(ass->GetScriptInfo("Aegisub Youtube Options"));
	wxStringInputStream stream(xml.empty() ? "<StyleOptions/>" : xml);
	if (!doc.Load(stream)) doc.SetRoot(new wxXmlNode(wxXML_ELEMENT_NODE, "StyleOptions"));
	return doc;
}
wxXmlNode *FindStyle(wxXmlDocument &doc, wxString const& name) {
	for (auto node = doc.GetRoot()->GetChildren(); node; node = node->GetNext())
		for (auto child = node->GetChildren(); child; child = child->GetNext())
			if (child->GetName() == "Name" && child->GetNodeContent() == name) return node;
	return nullptr;
}
wxString Value(wxXmlNode *node, wxString const& key) {
	if (node) for (auto child = node->GetChildren(); child; child = child->GetNext())
		if (child->GetName() == key) return child->GetNodeContent();
	return "";
}
}

wxPanel *DialogYoutube::MakeOptions(wxWindow *parent) {
	auto panel = new wxScrolledWindow(parent); panel->SetScrollRate(0, 10);
	auto layout = new wxBoxSizer(wxVERTICAL);
	layout->Add(new wxStaticText(panel, -1, wxS("프로젝트별 설정은 ASS에 저장됩니다. 미리보기와 내보내기에 같은 설정을 사용합니다.")), 0, wxALL, 12);
	style = new wxChoice(panel, -1);
	for (auto const& name : c->ass->GetStyles()) style->Append(to_wx(name));
	if (style->GetCount()) style->SetSelection(0);
	layout->Add(style, 0, wxALL | wxEXPAND, 12);
	glow = new wxCheckBox(panel, -1, wxS("외곽 광선 (Glow)"));
	bevel = new wxCheckBox(panel, -1, wxS("입체 테두리 (Bevel)"));
	soft = new wxCheckBox(panel, -1, wxS("부드러운 그림자"));
	hard = new wxCheckBox(panel, -1, wxS("단단한 그림자"));
	auto shadows = new wxBoxSizer(wxHORIZONTAL);
	for (auto box : {glow, bevel, soft, hard}) shadows->Add(box, 0, wxRIGHT, 12);
	layout->Add(shadows, 0, wxALL, 12);
	karaoke = new wxCheckBox(panel, -1, wxS("현재 가라오케 음절 강조"));
	layout->Add(karaoke, 0, wxALL, 12);
	highlight = new wxTextCtrl(panel, -1, "#FFFF00");
	layout->Add(new wxStaticText(panel, -1, wxS("현재 음절 글자색 (#RRGGBB)")), 0, wxLEFT, 12);
	layout->Add(highlight, 0, wxALL | wxEXPAND, 12);
	auto profile = new wxBoxSizer(wxHORIZONTAL);
	profile->Add(new wxStaticText(panel, -1, wxS("출력 배율")), 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, 6);
	scale = new wxSpinCtrlDouble(panel, -1, "1", wxDefaultPosition, wxSize(85, -1), wxSP_ARROW_KEYS, 0.1, 4, 1, 0.1);
	profile->Add(scale, 0, wxRIGHT, 12);
	profile->Add(new wxStaticText(panel, -1, wxS("명시적 위치 이동 X / Y")), 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, 6);
	offset_x = new wxSpinCtrl(panel, -1, "0", wxDefaultPosition, wxSize(85, -1), wxSP_ARROW_KEYS, -100000, 100000, 0);
	offset_y = new wxSpinCtrl(panel, -1, "0", wxDefaultPosition, wxSize(85, -1), wxSP_ARROW_KEYS, -100000, 100000, 0);
	profile->Add(offset_x, 0, wxRIGHT, 6); profile->Add(offset_y);
	layout->Add(profile, 0, wxALL, 12);
	mobile = new wxCheckBox(panel, -1, wxS("모바일 단순화 출력: 효과·위치 제거, 흰 글자·검은 배경·하단 중앙"));
	layout->Add(mobile, 0, wxLEFT | wxRIGHT, 12);
	auto save = new wxButton(panel, -1, wxS("스타일·출력 설정 적용 (실행 취소 가능)"));
	layout->Add(save, 0, wxALL, 12);
	resolution = new wxStaticText(panel, -1, "");
	layout->Add(resolution, 0, wxALL, 12);
	panel->SetSizer(layout);
	style->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) { LoadStyle(); });
	save->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { SaveStyle(); });
	LoadStyle();
	return panel;
}

void DialogYoutube::LoadStyle() {
	int w, h; c->ass->GetResolution(w, h);
	resolution->SetLabel(wxString::Format(wxS("현재 좌표계 %d × %d · 영상 해상도를 변경하지 않습니다.\n글자 크기는 Default 스타일을 기준으로 계산됩니다.\n위치 이동은 명시적 위치에만 적용하며 모바일 단순화에서는 무시됩니다.\nAndroid 글자 크기·배경·그림자는 실제 기기에서 별도로 확인하세요."), w, h));
	auto doc = Options(c->ass.get());
	auto node = FindStyle(doc, style->GetStringSelection());
	auto shadows = Value(node, "ShadowType");
	auto base = c->ass->GetStyle(from_wx(style->GetStringSelection()));
	glow->SetValue(node ? shadows.Contains("Glow") : base && base->outline_w > 0 && base->borderstyle != 3);
	soft->SetValue(node ? shadows.Contains("SoftShadow") : base && base->shadow_w > 0);
	hard->SetValue(shadows.Contains("HardShadow")); bevel->SetValue(shadows.Contains("Bevel"));
	karaoke->SetValue(Value(node, "IsKaraoke") == "true");
	auto color = Value(node, "CurrentWordTextColor");
	highlight->SetValue(color.empty() ? "#FFFF00" : color);
	for (auto output = doc.GetRoot()->GetChildren(); output; output = output->GetNext()) if (output->GetName() == "Output") {
		double value = 1; output->GetAttribute("Scale", "1").ToDouble(&value); scale->SetValue(value);
		long x = 0, y = 0; output->GetAttribute("OffsetX", "0").ToLong(&x); output->GetAttribute("OffsetY", "0").ToLong(&y);
		offset_x->SetValue(x); offset_y->SetValue(y); mobile->SetValue(output->GetAttribute("Mobile", "false") == "true"); return;
	}
	scale->SetValue(1); offset_x->SetValue(0); offset_y->SetValue(0); mobile->SetValue(false);
}

void DialogYoutube::SaveStyle() {
	if (style->GetSelection() == wxNOT_FOUND) return;
	wxColour color(highlight->GetValue());
	if (!color.IsOk()) { status->SetLabel(wxS("올바른 강조색을 입력하세요 (#RRGGBB).")); return; }
	auto doc = Options(c->ass.get());
	auto node = FindStyle(doc, style->GetStringSelection());
	if (!node) { node = new wxXmlNode(wxXML_ELEMENT_NODE, "Style"); doc.GetRoot()->AddChild(node); }
	auto add = [node](wxString const& key, wxString const& value) {
		for (auto old = node->GetChildren(); old; old = old->GetNext()) {
			if (old->GetName() == key) { node->RemoveChild(old); delete old; break; }
		}
		auto child = new wxXmlNode(wxXML_ELEMENT_NODE, key);
		child->AddChild(new wxXmlNode(wxXML_TEXT_NODE, "", value)); node->AddChild(child);
	};
	add("Name", style->GetStringSelection());
	wxString shadows;
	if (glow->GetValue()) shadows += "Glow ";
	if (bevel->GetValue()) shadows += "Bevel ";
	if (soft->GetValue()) shadows += "SoftShadow ";
	if (hard->GetValue()) shadows += "HardShadow ";
	add("ShadowType", shadows.empty() ? "None" : shadows.Trim());
	add("IsKaraoke", karaoke->GetValue() ? "true" : "false");
	add("CurrentWordTextColor", color.GetAsString(wxC2S_HTML_SYNTAX));
	wxXmlNode *output = nullptr;
	for (auto child = doc.GetRoot()->GetChildren(); child; child = child->GetNext()) if (child->GetName() == "Output") output = child;
	if (!output) { output = new wxXmlNode(wxXML_ELEMENT_NODE, "Output"); doc.GetRoot()->AddChild(output); }
	for (auto key : {"Scale", "OffsetX", "OffsetY", "Mobile"}) output->DeleteAttribute(key);
	output->AddAttribute("Scale", wxString::Format("%.2f", scale->GetValue()));
	output->AddAttribute("OffsetX", wxString::Format("%d", offset_x->GetValue()));
	output->AddAttribute("OffsetY", wxString::Format("%d", offset_y->GetValue()));
	output->AddAttribute("Mobile", mobile->GetValue() ? "true" : "false");
	wxStringOutputStream stream; doc.Save(stream, 0);
	auto xml = stream.GetString(); xml.Replace("\n", ""); xml.Replace("\r", "");
	c->ass->SetScriptInfo("Aegisub Youtube Options", from_wx(xml));
	c->ass->Commit(wxS("YouTube 스타일 변환 설정"), AssFile::COMMIT_SCRIPTINFO);
}
