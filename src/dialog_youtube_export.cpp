#include "dialog_youtube.h"
#include "compat.h"
#include "youtube_process.h"
#include <wx/button.h>
#include <wx/choicdlg.h>
#include <wx/dirdlg.h>
#include <wx/file.h>
#include <wx/filedlg.h>
#include <wx/filename.h>
#include <wx/msgdlg.h>
#include <wx/process.h>
#include <wx/stattext.h>
#include <wx/textctrl.h>

void DialogYoutube::Export() {
	if (ready_revision != revision) return;
	wxArrayString names;
	names.Add(wxS("YouTube YTT (변환 미리보기와 동일 파일)"));
	names.Add(wxS("호환 SRT (스타일·위치·효과는 보존되지 않음)"));
	names.Add(wxS("편집 원본 ASS (변환 설정 포함)"));
	wxMultiChoiceDialog choices(this, wxS("전달할 파일을 선택하세요."), wxS("내보내기"), names);
	choices.SetMinSize(wxSize(660, 260)); choices.SetSize(660, 260);
	wxArrayInt selected; selected.Add(0); selected.Add(2); choices.SetSelections(selected);
	if (choices.ShowModal() != wxID_OK || choices.GetSelections().empty()) return;
	wxDirDialog folder(this, wxS("새 전달 폴더를 만들 위치 선택"));
	if (folder.ShowModal() != wxID_OK || ready_revision != revision) return;
	auto stamp = wxDateTime::Now().Format("%Y-%m-%d-%H-%M-%S-");
	auto destination = folder.GetPath() + "/" + stamp + "YouTube";
	if (wxDirExists(destination) || !wxFileName::Mkdir(destination, 0700)) {
		wxMessageBox(wxS("출력 폴더가 이미 있거나 만들 수 없습니다."), wxS("내보내기 실패"), wxOK | wxICON_ERROR, this); return;
	}
	const wxString files[] = {"result.ytt", "compatible.srt", "source.ass"};
	for (auto index : choices.GetSelections()) if (!wxCopyFile(ready_dir + "/" + files[index], destination + "/" + files[index], false)) {
		wxMessageBox(wxS("파일 복사 실패: ") + files[index], wxS("내보내기 실패"), wxOK | wxICON_ERROR, this); return;
	}
	if (!wxCopyFile(ready_dir + "/manifest.json", destination + "/manifest.json", false)) {
		wxMessageBox(wxS("파일 복사 실패: manifest.json"), wxS("내보내기 실패"), wxOK | wxICON_ERROR, this); return;
	}
	wxFile guide(destination + "/" + stamp + wxS("적용-안내.ko.txt"), wxFile::write);
	if (!guide.IsOpened() || !guide.Write(wxS("YouTube 자막 적용 안내\n\nresult.ytt: YouTube용 스타일 자막\ncompatible.srt: 스타일 없는 호환 자막\nsource.ass: Aegisub 편집 원본\n\nYouTube Studio에서 해당 영상의 자막 언어를 선택하고 타이밍 포함 파일 업로드로 YTT를 선택하세요.\n이 기능은 업로드·게시를 대신 수행하지 않습니다. 채널 담당자가 검토 후 게시하세요.\nStudio 편집기에서 수정·재저장하면 스타일이 유실될 수 있습니다. 이는 고정한 YTSubConverter README의 주의사항이며 현재 Studio 재저장은 이 앱에서 실증하지 않았습니다.\n편집기 안의 기본 텍스트 미리보기와 실제 재생 화면은 다를 수 있습니다.\n원본 ASS를 유지하고 실제 데스크톱·Android·iOS 플레이어를 각각 확인하세요.\nAegisub의 YouTube 보기는 실제 YTT에서 만든 시각적 근사치입니다. 모바일 검증을 대신하지 않습니다.\n")) || !guide.Close()) {
		wxMessageBox(wxS("적용 안내 파일 저장 실패"), wxS("내보내기 실패"), wxOK | wxICON_ERROR, this); return;
	}
	status->SetLabel(wxS("내보냄: ") + stamp + wxS("YouTube\n선택한 위치에 자막 파일과 적용 안내를 저장했습니다."));
}

void DialogYoutube::Import() {
	if (import_pid) { status->SetLabel(wxS("가져오기 진행 중입니다. 변환 취소 버튼으로 취소할 수 있습니다.")); return; }
	wxFileDialog input(this, wxS("YTT/SRV3에서 편집용 ASS 만들기"), "", "", wxS("YouTube 자막|*.ytt;*.srv3"), wxFD_OPEN | wxFD_FILE_MUST_EXIST);
	if (input.ShowModal() != wxID_OK) return;
	wxFileDialog output(this, wxS("새 편집용 ASS 경로 (현재 문서는 유지)"), "", "imported.ass", "ASS|*.ass", wxFD_SAVE);
	if (output.ShowModal() != wxID_OK) return;
	if (wxFileExists(output.GetPath())) { wxMessageBox(wxS("원본 보호를 위해 새 파일명을 선택하세요."), wxS("가져오기"), wxOK, this); return; }
	wxArrayString args; args.Add(Helper()); args.Add("import"); args.Add(input.GetPath()); args.Add(output.GetPath());
	import_output = output.GetPath();
	importer = new wxProcess(this); importer->Redirect();
	import_pid = ExecuteYoutube(args, wxEXEC_ASYNC | wxEXEC_MAKE_GROUP_LEADER, importer);
	if (!import_pid) { delete importer; importer = nullptr; status->SetLabel(wxS("가져오기 시작 실패")); return; }
	status->SetLabel(wxS("편집용 ASS 생성 중… 완료 후 파일 → 자막 열기로 여세요. 현재 문서는 유지됩니다."));
}

void DialogYoutube::StartPlayer() {
	if (ready_revision != revision || player_pid) return;
	wxFileName::Mkdir(root + "/player", 0700);
	if (wxFileExists(root + "/player/stop")) wxRemoveFile(root + "/player/stop");
	if (wxFileExists(root + "/player/status.txt")) wxRemoveFile(root + "/player/status.txt");
	player = new wxProcess(this); player->Redirect();
	wxArrayString args; args.Add(Helper()); args.Add("player"); args.Add(url->GetValue());
	args.Add(root + "/current.ytt"); args.Add(language->GetValue()); args.Add(root + "/player");
	player_pid = ExecuteYoutube(args, wxEXEC_ASYNC, player);
	if (!player_pid) { delete player; player = nullptr; player_status->SetLabel(wxS("Chrome 시작 실패")); return; }
	player_status->SetLabel(wxS("플레이어 시작 중 · 선택한 언어의 기존 CC 트랙을 켜세요. 현재 YTT 응답 대체는 아직 확인되지 않았습니다."));
	player_poll.Start(1000);
}

void DialogYoutube::StopPlayer() {
	if (!player_pid) return;
	wxFile stop(root + "/player/stop", wxFile::write); stop.Write("stop");
}
