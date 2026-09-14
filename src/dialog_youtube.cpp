#include "dialog_youtube.h"
#include "ass_file.h"
#include "ass_dialogue.h"
#include "compat.h"
#include "include/aegisub/context.h"
#include "project.h"
#include "selection_controller.h"
#include "subtitle_format_ass.h"
#include "video_controller.h"
#include "youtube_process.h"
#include <boost/filesystem.hpp>
#include <libaegisub/json.h>
#include <libaegisub/io.h>
#include <libaegisub/cajun/reader.h>
#include <wx/button.h>
#include <wx/checkbox.h>
#include <wx/choice.h>
#include <wx/filename.h>
#include <wx/listctrl.h>
#include <wx/notebook.h>
#include <wx/process.h>
#include <wx/sizer.h>
#include <wx/stattext.h>
#include <wx/stdpaths.h>
#include <wx/textctrl.h>
#include <wx/txtstrm.h>
#include <wx/file.h>
#include <stdexcept>

DialogYoutube::DialogYoutube(agi::Context *context)
: wxDialog(context->parent, -1, wxS("YouTube 자막 · 변환과 비교"), wxDefaultPosition, wxSize(760, 670), wxDEFAULT_DIALOG_STYLE | wxRESIZE_BORDER)
, c(context), debounce(this), player_poll(this) {
	root = wxFileName::CreateTempFileName("aegisub-youtube-");
	wxRemoveFile(root);
	wxFileName::Mkdir(root, 0700);
	auto layout = new wxBoxSizer(wxVERTICAL);
	preview = new wxCheckBox(this, -1, wxS("영상 화면에서 YouTube 변환 결과 보기 (시각적 근사치)"));
	layout->Add(preview, 0, wxALL, 12);
	layout->Add(new wxStaticText(this, -1, wxS("체크를 끄면 같은 시각의 편집 원본을 봅니다. 재생·탐색은 기존 영상 도구를 사용하세요.")), 0, wxLEFT | wxRIGHT, 12);
	status = new wxStaticText(this, -1, wxS("변환 준비 중"));
	layout->Add(status, 0, wxALL | wxEXPAND, 12);
	auto book = new wxNotebook(this, -1);
	book->AddPage(MakeOptions(book), wxS("변환 설정"));
	book->AddPage(MakeEffects(book), wxS("선택 행 효과"));
	issues = new wxListCtrl(book, -1, wxDefaultPosition, wxDefaultSize, wxLC_REPORT | wxLC_SINGLE_SEL);
	issues->InsertColumn(0, wxS("행 / 시간"), wxLIST_FORMAT_LEFT, 125);
	issues->InsertColumn(1, wxS("태그 · 원인 · 보기 환경 (두 번 클릭하여 이동)"), wxLIST_FORMAT_LEFT, 580);
	book->AddPage(issues, wxS("호환성 진단"));
	layout->Add(book, 1, wxEXPAND | wxLEFT | wxRIGHT, 12);
	auto browser_row = new wxBoxSizer(wxHORIZONTAL);
	url = new wxTextCtrl(this, -1, "https://www.youtube.com/watch?v=");
	url->SetHint(wxS("YouTube 영상 URL"));
	language = new wxTextCtrl(this, -1, "en", wxDefaultPosition, wxSize(55, -1));
	language->SetToolTip(wxS("대체할 기존 수동 자막의 언어 코드 (en, ko 등). 자동 생성·자동 번역 트랙은 제외됩니다."));
	player_button = new wxButton(this, -1, wxS("실제 플레이어 시작"));
	auto stop_player = new wxButton(this, -1, wxS("플레이어 종료"));
	browser_row->Add(url, 1, wxRIGHT, 5);
	browser_row->Add(language, 0, wxRIGHT, 5);
	browser_row->Add(player_button, 0, wxRIGHT, 5);
	browser_row->Add(stop_player);
	layout->Add(browser_row, 0, wxALL | wxEXPAND, 12);
	player_status = new wxStaticText(this, -1, wxS("전용 Chrome에서 기존 자막 트랙을 켜세요. 실제 모바일 기기 검증은 별도로 필요합니다."));
	layout->Add(player_status, 0, wxLEFT | wxRIGHT | wxEXPAND, 12);
	auto buttons = new wxBoxSizer(wxHORIZONTAL);
	auto refresh = new wxButton(this, -1, wxS("다시 변환"));
	auto cancel = new wxButton(this, -1, wxS("변환 취소"));
	auto import = new wxButton(this, -1, wxS("YTT → 편집용 ASS"));
	export_button = new wxButton(this, -1, wxS("내보내기 묶음…"));
	auto edit = new wxButton(this, -1, wxS("영상·자막 편집"));
	edit->SetToolTip(wxS("창을 숨기고 편집합니다. 자동 변환은 계속됩니다. 파일 메뉴에서 다시 여세요."));
	edit->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { Hide(); c->parent->SetFocus(); });
	for (auto button : {refresh, cancel, import, export_button, edit}) buttons->Add(button, 0, wxRIGHT, 8);
	layout->Add(buttons, 0, wxALL, 12);
	SetSizer(layout);
	SetMinSize(wxSize(760, 670));
	preview->Bind(wxEVT_CHECKBOX, [this](wxCommandEvent&) { UpdateView(); });
	refresh->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { Invalidate(); });
	cancel->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
		if (import_pid) wxProcess::Kill(import_pid, wxSIGKILL, wxKILL_CHILDREN);
		Invalidate(); pending = false; debounce.Stop(); status->SetLabel(wxS("취소됨 · 최신 결과가 없습니다."));
	});
	export_button->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { Export(); });
	import->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { Import(); });
	player_button->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { StartPlayer(); });
	stop_player->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { StopPlayer(); });
	issues->Bind(wxEVT_LIST_ITEM_ACTIVATED, [this](wxListEvent &event) {
		auto index = static_cast<size_t>(event.GetIndex());
		if (index >= issue_ids.size()) return;
		for (auto &line : c->ass->Events) if (line.Id == issue_ids[index]) {
			c->selectionController->SetSelectionAndActive({&line}, &line);
			c->videoController->JumpToTime(line.Start); break;
		}
	});
	Bind(wxEVT_TIMER, [this](wxTimerEvent&) { if (pending && !pid) StartConversion(); }, debounce.GetId());
	Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
		if (ready_revision != revision) return;
		if (!wxFileExists(root + "/player/status.txt")) return;
		wxFile file(root + "/player/status.txt"); wxString message;
		if (!file.IsOpened() || !file.ReadAll(&message)) return;
		if (message.StartsWith("SHA256 " + ready_hash + "\n")) player_status->SetLabel(message.AfterFirst('\n'));
		else if (message.Contains(wxS("오류")) || message.Contains(wxS("실패"))) player_status->SetLabel(wxS("플레이어 세션: ") + message);
	}, player_poll.GetId());
	Bind(wxEVT_END_PROCESS, [this](wxProcessEvent &event) {
		auto finished_pid = event.GetPid(); auto exit_code = event.GetExitCode();
		CallAfter([this, finished_pid, exit_code] { wxProcessEvent finished(0, finished_pid, exit_code); Finish(finished); });
	});
	commit_connection = c->ass->AddCommitListener([this](int type, const AssDialogue*) {
		if (type & (AssFile::COMMIT_SCRIPTINFO | AssFile::COMMIT_STYLES) || type == AssFile::COMMIT_NEW) {
			auto selected = style->GetStringSelection();
			style->Clear();
			for (auto const& name : c->ass->GetStyles()) style->Append(to_wx(name));
			if (!style->SetStringSelection(selected) && style->GetCount()) style->SetSelection(0);
			LoadStyle();
		}
		Invalidate();
	});
	Invalidate();
}

DialogYoutube::~DialogYoutube() {
	closing = true;
	commit_connection.Disconnect();
	debounce.Stop(); player_poll.Stop();
	if (process) { process->Detach(); if (pid) wxProcess::Kill(pid, wxSIGKILL, wxKILL_CHILDREN); }
	if (importer) { importer->Detach(); if (import_pid) wxProcess::Kill(import_pid, wxSIGKILL, wxKILL_CHILDREN); }
	StopPlayer();
	if (player) player->Detach();
	c->videoController->SetPreviewSubtitles(nullptr);
	// Running helpers own files until exit; temporary session files are kept if still running.
	if (!pid && !player_pid && !import_pid) boost::filesystem::remove_all(from_wx(root));
}

wxString DialogYoutube::Helper() const {
	wxString configured;
	if (wxGetEnv("AEGISUB_YOUTUBE_HELPER", &configured)) return configured;
#ifdef _WIN32
	return wxFileName(wxStandardPaths::Get().GetExecutablePath()).GetPath() + "/youtube/aegisub-youtube.exe";
#else
	return wxFileName(wxStandardPaths::Get().GetExecutablePath()).GetPath() + "/youtube/aegisub-youtube";
#endif
}

void DialogYoutube::Invalidate() {
	++revision; ready_revision = 0; visual.reset(); pending = true;
	edited = std::chrono::steady_clock::now();
	export_button->Disable(); player_button->Disable();
	status->SetLabel(wxS("편집됨 · 변환 대기 중 (이전 결과 사용 안 함)"));
	if (wxFileExists(root + "/current.ytt")) wxRemoveFile(root + "/current.ytt");
	if (wxFileExists(root + "/player/status.txt")) wxRemoveFile(root + "/player/status.txt");
	if (player_pid) player_status->SetLabel(wxS("편집됨 · 최신 결과 변환 대기 중. 플레이어에는 이전 자막이 남아 있을 수 있습니다."));
	if (pid) wxProcess::Kill(pid, wxSIGKILL, wxKILL_CHILDREN);
	UpdateView();
	debounce.StartOnce(300);
}

void DialogYoutube::UpdateView() {
	if (!preview->GetValue()) { c->videoController->SetPreviewSubtitles(nullptr); return; }
	if (visual) c->videoController->SetPreviewSubtitles(visual);
	else {
		auto blank = std::make_shared<AssFile>(); blank->LoadDefault(false);
		c->videoController->SetPreviewSubtitles(blank);
	}
}

void DialogYoutube::StartConversion() {
	pending = false; running_revision = revision;
	Diagnose();
	if (!wxFileExists(Helper())) { status->SetLabel(wxS("변환 엔진이 없습니다. YouTube 보조 프로그램을 포함한 패키지를 사용하세요.")); return; }
	running_dir = root + wxString::Format("/revision-%u", revision);
	wxFileName::Mkdir(running_dir, 0700);
	try {
		AssFile snapshot(*c->ass);
		AssSubtitleFormat().WriteFile(&snapshot, from_wx(running_dir + "/input.ass"), c->project->Timecodes(), "utf-8");
		wxString xml = to_wx(c->ass->GetScriptInfo("Aegisub Youtube Options"));
		if (xml.empty()) xml = "<StyleOptions/>";
		wxFile options(running_dir + "/options.xml", wxFile::write);
		if (!options.IsOpened() || !options.Write(xml) || !options.Close())
			throw std::runtime_error(u8"변환 설정 파일 저장 실패");
		process = new wxProcess(this); process->Redirect();
		wxArrayString arguments;
		arguments.Add(Helper()); arguments.Add("preview"); arguments.Add(running_dir + "/input.ass");
		arguments.Add(running_dir); arguments.Add(running_dir + "/options.xml");
		pid = ExecuteYoutube(arguments, wxEXEC_ASYNC | wxEXEC_MAKE_GROUP_LEADER, process);
		if (!pid) { delete process; process = nullptr; status->SetLabel(wxS("변환 프로세스를 시작하지 못했습니다.")); return; }
		status->SetLabel(wxS("변환 중… 취소할 수 있습니다."));
	} catch (std::exception const& error) { status->SetLabel(to_wx(error.what())); }
}

void DialogYoutube::Finish(wxProcessEvent &event) {
	if (event.GetPid() == import_pid) {
		import_pid = 0;
		wxString error;
		if (importer->IsErrorAvailable()) { wxTextInputStream stream(*importer->GetErrorStream()); error = stream.ReadLine(); }
		delete importer; importer = nullptr;
		status->SetLabel(event.GetExitCode() == 0 ? wxS("편집용 ASS 생성됨: ") + wxFileName(import_output).GetFullName() : wxS("가져오기 실패 또는 취소: ") + error);
		return;
	}
	if (event.GetPid() == player_pid) {
		player_pid = 0; player_poll.Stop();
		wxString error;
		if (player->IsErrorAvailable()) { wxTextInputStream stream(*player->GetErrorStream()); error = stream.ReadLine(); }
		delete player; player = nullptr;
		player_status->SetLabel(error.empty() ? wxString(wxS("플레이어 세션 종료됨")) : error); return;
	}
	if (event.GetPid() != pid) return;
	pid = 0;
	wxString error;
	if (process->IsErrorAvailable()) { wxTextInputStream stream(*process->GetErrorStream()); error = stream.ReadLine(); }
	delete process; process = nullptr;
	if (running_revision != revision) { if (pending) debounce.StartOnce(100); return; }
	if (event.GetExitCode() != 0) { status->SetLabel(wxS("변환 실패: ") + error); return; }
	try {
		auto result = std::make_shared<AssFile>();
		AssSubtitleFormat().ReadFile(result.get(), from_wx(running_dir + "/preview.visual.ass"), c->project->Timecodes(), "utf-8");
		json::UnknownElement manifest;
		json::Reader::Read(manifest, *agi::io::Open(from_wx(running_dir + "/manifest.json")));
		json::Object& metrics = manifest;
		json::Object& output_profile = metrics["profile"];
		auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - edited).count();
		auto summary = wxString::Format(wxS("최신 변환 완료 · 입력 후 %lld ms · %s bytes · 시각적 근사치"), (long long)elapsed,
			wxFileName(running_dir + "/result.ytt").GetSize().ToString());
		summary += wxString::Format(wxS("\n입력 %lld행 → 확장 %lld개 · 초당 %s개 · %s"),
			(long long)(int64_t)metrics["inputEvents"], (long long)(int64_t)metrics["expandedEvents"], to_wx(static_cast<std::string&>(metrics["eventDensity"])),
			(bool)output_profile["Mobile"] ? wxS("모바일 단순화 (실기기 미검증)") : wxS("원본 스타일 출력"));
		if (!wxCopyFile(running_dir + "/result.ytt", root + "/current.ytt.tmp", true) ||
			!wxRenameFile(root + "/current.ytt.tmp", root + "/current.ytt", true)) throw std::runtime_error(u8"YTT 결과 파일 적용 실패");
		visual = std::move(result); ready_dir = running_dir; ready_revision = revision;
		ready_hash = to_wx(static_cast<std::string&>(metrics["yttSha256"]));
		status->SetLabel(summary);
		if (player_pid) player_status->SetLabel(wxS("최신 결과 준비됨 · CC를 껐다 켜세요. 현재 YTT 응답 대체는 아직 확인되지 않았습니다."));
		export_button->Enable(); player_button->Enable();
		UpdateView();
	} catch (std::exception const& error) {
		visual.reset(); ready_revision = 0; export_button->Disable(); player_button->Disable();
		if (wxFileExists(root + "/current.ytt")) wxRemoveFile(root + "/current.ytt");
		UpdateView(); status->SetLabel(wxS("미리보기 로드 실패: ") + to_wx(error.what()));
	}
}
