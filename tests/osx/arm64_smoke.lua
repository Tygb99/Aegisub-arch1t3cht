script_name = "ARM64 smoke: LuaJIT + native modules"
script_description = "ARM64·Lua 5.2 호환·native 모듈·MoonScript를 검사하고 선택 첫 줄에 표식을 추가합니다."
script_author = "Aegisub QA"
script_version = "1.0"

local function log(message)
    aegisub.debug.out(0, "%s\n", message)
end

local function validate(subtitles, selected)
    return selected[1] ~= nil and subtitles[selected[1]].class == "dialogue"
end

local function run(subtitles, selected)
    log("ARM64_SMOKE BEGIN version=" .. script_version)
    if not validate(subtitles, selected) then
        log("RESULT=FAIL CODE=1 reason=INVALID_SELECTION")
        error("검사할 대사 줄을 선택하세요.", 0)
    end

    local failures = 0
    local function check(name, test)
        local ok, detail = pcall(test)
        if not ok then failures = failures + 1 end
        log((ok and "PASS " or "FAIL ") .. name .. ": " .. tostring(detail))
    end

    check("LuaJIT ARM64", function()
        local runtime = require("jit")
        assert(runtime.arch == "arm64", "jit.arch=" .. tostring(runtime.arch))
        assert(runtime.os == "OSX", "jit.os=" .. tostring(runtime.os))
        return runtime.version .. " arch=" .. runtime.arch .. " os=" .. runtime.os
            .. " ABI=" .. _VERSION .. " jit=" .. tostring(runtime.status())
    end)

    check("LUA52COMPAT table.pack/unpack", function()
        local packed = table.pack("한글", nil, 52)
        local a, b, c = table.unpack(packed, 1, packed.n)
        assert(packed.n == 3 and a == "한글" and b == nil and c == 52)
        return "nil을 포함한 3개 값 복원"
    end)

    check("LUA52COMPAT __len/rawlen/__pairs", function()
        local value = setmetatable({1, 2}, {
            __len = function() return 52 end,
            __pairs = function() return next, {compat = 52}, nil end
        })
        assert(#value == 52 and rawlen(value) == 2)
        local count = 0
        for key, item in pairs(value) do
            assert(key == "compat" and item == 52)
            count = count + 1
        end
        assert(count == 1)
        return "__len=52 rawlen=2 __pairs=compat:52"
    end)

    check("LUA52COMPAT package.searchers/coroutine", function()
        assert(type(package.searchers) == "table" and package.searchers == package.loaders)
        local co = coroutine.create(function() return coroutine.running() end)
        local ok, thread, is_main = coroutine.resume(co)
        assert(ok and thread == co and is_main == false)
        return "searchers=loaders, coroutine.running()의 두 반환값 확인"
    end)

    check("lpeg native", function()
        local lpeg = require("lpeg")
        assert(debug.getinfo(lpeg.match).what == "C")
        local pattern = lpeg.P("한글") * lpeg.C(lpeg.R("09")^1) * -lpeg.P(1)
        assert(lpeg.match(pattern, "한글123") == "123")
        assert(lpeg.match(pattern, "한글x") == nil)
        return "한글123 → 123, 잘못된 입력 거부"
    end)

    check("lfs native", function()
        local lfs = require("lfs")
        assert(debug.getinfo(package.preload["aegisub.__lfs_impl"]).what == "C")
        local cwd = assert(lfs.currentdir())
        assert(lfs.attributes(cwd, "mode") == "directory")
        return "currentdir/attributes: " .. cwd
    end)

    check("re native", function()
        local re = require("re")
        assert(type(require("aegisub.__re_impl").compile) == "cdata")
        assert(re.sub("한글123", "[0-9]+", "456") == "한글456")
        return "한글123 → 한글456"
    end)

    check("unicode native", function()
        local unicode = require("unicode")
        assert(type(require("aegisub.__unicode_impl").to_upper_case) == "cdata")
        assert(unicode.len("한글🙂") == 3 and unicode.codepoint("한") == 0xD55C)
        assert(unicode.to_upper_case("straße") == "STRASSE")
        return "UTF-8 길이=3 U+D55C, Straße 대문자 변환"
    end)

    check("luabins native", function()
        local luabins = require("luabins")
        assert(debug.getinfo(luabins.save).what == "C" and debug.getinfo(luabins.load).what == "C")
        local blob = assert(luabins.save({text = "한글", answer = 42}, nil, true))
        local ok, value, missing, flag = luabins.load(blob)
        assert(ok and value.text == "한글" and value.answer == 42 and missing == nil and flag == true)
        assert(luabins.load("invalid") == nil)
        return "table/nil/bool 직렬화 왕복, 잘못된 데이터 거부"
    end)

    check("MoonScript", function()
        local moon = require("moonscript")
        local compiled = assert(moon.loadstring("square = (x) -> x * x\nsquare 7"))
        assert(compiled() == 49)
        assert(moon.loadstring("if !!!") == nil)
        return "컴파일·실행=49, 문법 오류 거부"
    end)

    if failures > 0 then
        log("RESULT=FAIL CODE=1 failed_checks=" .. failures)
        error("ARM64 검사 실패: " .. failures .. "개. 자막을 변경하지 않았습니다.", 0)
    end

    local index = selected[1]
    local line = subtitles[index]
    line.text = line.text .. " [Lua ARM64]"
    subtitles[index] = line
    aegisub.set_undo_point(script_name)
    log("MACRO selected_first=" .. index .. " text=" .. line.text)
    log("RESULT=PASS CODE=0 checks=10 modified_lines=1")
    return selected, index
end

aegisub.register_macro(script_name, script_description, run, validate)
