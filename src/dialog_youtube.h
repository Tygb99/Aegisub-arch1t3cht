#pragma once

#include <libaegisub/signal.h>
#include <wx/dialog.h>
#include <wx/timer.h>
#include <chrono>
#include <memory>
#include <vector>

namespace agi { struct Context; }
class AssFile;
class wxCheckBox;
class wxChoice;
class wxButton;
class wxListCtrl;
class wxPanel;
class wxProcess;
class wxProcessEvent;
class wxSpinCtrl;
class wxSpinCtrlDouble;
class wxStaticText;
class wxTextCtrl;

class DialogYoutube final : public wxDialog {
	agi::Context *c;
	agi::signal::Connection commit_connection;
	wxTimer debounce;
	wxTimer player_poll;
	wxProcess *process = nullptr;
	wxProcess *player = nullptr;
	wxProcess *importer = nullptr;
	long import_pid = 0;
	wxString import_output;
	long pid = 0;
	long player_pid = 0;
	unsigned revision = 0, running_revision = 0, ready_revision = 0;
	bool pending = false;
	bool closing = false;
	wxString root, running_dir, ready_dir, ready_hash;
	std::chrono::steady_clock::time_point edited;
	std::shared_ptr<AssFile> visual;
	wxCheckBox *preview;
	wxStaticText *status;
	wxStaticText *player_status;
	wxStaticText *resolution;
	wxButton *export_button;
	wxButton *player_button;
	wxTextCtrl *url;
	wxTextCtrl *language;
	wxListCtrl *issues;
	std::vector<int> issue_ids;
	wxChoice *style;
	wxCheckBox *glow, *bevel, *soft, *hard, *karaoke;
	wxTextCtrl *highlight;
	wxSpinCtrlDouble *scale;
	wxSpinCtrl *offset_x, *offset_y;
	wxCheckBox *mobile;

	void Invalidate();
	void StartConversion();
	void Finish(wxProcessEvent &event);
	void UpdateView();
	void Export();
	void Import();
	void StartPlayer();
	void StopPlayer();
	void Diagnose();
	void LoadStyle();
	void SaveStyle();
	wxPanel *MakeEffects(wxWindow *parent);
	wxPanel *MakeOptions(wxWindow *parent);
	wxString Helper() const;
public:
	explicit DialogYoutube(agi::Context *context);
	~DialogYoutube();
};
