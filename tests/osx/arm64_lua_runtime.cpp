#include <libaegisub/dispatch.h>
#include <libaegisub/log.h>
#include <libaegisub/lua/modules.h>
#include <libaegisub/lua/script_reader.h>
#include <libaegisub/lua/utils.h>

#include <boost/locale/generator.hpp>
#include <iostream>
#include <memory>
#include <stdexcept>

namespace {
void check(lua_State *state, bool success) {
	if (!success) throw std::runtime_error(agi::lua::get_string_or_default(state, -1));
}
}

int main(int argc, char **argv) try {
	if (argc == 2 && std::string(argv[1]) == "--help") {
		std::cout << "Usage: arm64_lua_runtime INCLUDE_DIRECTORY SCRIPT [SCRIPT_ARGS...]\n";
		return 0;
	}
	if (argc < 3) throw std::runtime_error("Expected include directory and Lua/MoonScript file");
	std::locale::global(boost::locale::generator().generate(""));
	agi::dispatch::Init([](agi::dispatch::Thunk) { throw std::runtime_error("Unexpected UI dispatch"); });
	agi::log::LogSink log;
	agi::log::log = &log;
	std::unique_ptr<lua_State, decltype(&lua_close)> state(luaL_newstate(), lua_close);
	if (!state) throw std::runtime_error("Cannot create embedded LuaJIT state");
	auto *L = state.get();
	agi::lua::preload_modules(L);
	lua_pushnil(L);
	lua_setglobal(L, "dofile");
	lua_pushnil(L);
	lua_setglobal(L, "loadfile");
	lua_getglobal(L, "package");
	lua_pushliteral(L, "");
	lua_setfield(L, -2, "path");
	lua_pushliteral(L, "");
	lua_setfield(L, -2, "cpath");
	lua_pop(L, 1);
	check(L, agi::lua::Install(L, {argv[1]}));
	lua_createtable(L, argc - 3, 1);
	for (int i = 2; i < argc; ++i) {
		lua_pushstring(L, argv[i]);
		lua_rawseti(L, -2, i - 2);
	}
	lua_setglobal(L, "arg");
	lua_pushcfunction(L, agi::lua::add_stack_trace);
	check(L, agi::lua::LoadFile(L, argv[2]));
	check(L, lua_pcall(L, 0, 0, 1) == 0);
	return 0;
} catch (const agi::Exception &error) {
	std::cerr << "FAIL: " << error.GetMessage() << '\n';
	return 1;
} catch (const std::exception &error) {
	std::cerr << "FAIL: " << error.what() << '\n';
	return 1;
}
