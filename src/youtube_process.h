#pragma once
#include <wx/utils.h>
#include <wx/arrstr.h>
#include <string>
#include <vector>

inline long ExecuteYoutube(wxArrayString const& arguments, int flags, wxProcess *process = nullptr) {
	std::vector<std::wstring> strings;
	for (auto const& argument : arguments) strings.push_back(argument.ToStdWstring());
	std::vector<wchar_t*> argv;
	for (auto& argument : strings) argv.push_back(argument.data());
	argv.push_back(nullptr);
	return wxExecute(argv.data(), flags, process);
}
