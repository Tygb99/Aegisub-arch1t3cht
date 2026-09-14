local fixture = assert(arg[1], "GUI fixture 경로가 필요합니다.")
local registered, undo_count, last_log = nil, 0, nil

aegisub = {
    register_macro = function(name, description, run, validate)
        assert(registered == nil and type(description) == "string")
        registered = {name = name, run = run, validate = validate}
    end,
    debug = {out = function(level, format, ...)
        assert(level == 0)
        last_log = string.format(format, ...)
        io.write(last_log)
    end},
    set_undo_point = function(name)
        assert(name == registered.name)
        undo_count = undo_count + 1
    end
}

local file = assert(io.open(fixture, "rb"))
local source = assert(file:read("*a"))
file:close()
assert(loadstring(source, "@" .. fixture))()
assert(registered and type(registered.run) == "function" and type(registered.validate) == "function")

local rows = {
    {class = "info", text = "metadata"},
    {class = "dialogue", text = "첫 선택 줄", start_time = 1000, end_time = 2000, style = "Default"},
    {class = "dialogue", text = "다른 선택 줄", start_time = 3000, end_time = 4000, style = "Other"}
}
local writes = 0
local subtitles = setmetatable({}, {
    __index = function(_, index)
        local copy = {}
        for key, value in pairs(assert(rows[index])) do copy[key] = value end
        return copy
    end,
    __newindex = function(_, index, line)
        writes = writes + 1
        rows[index] = line
    end
})
local selected = {2, 3}
assert(registered.validate(subtitles, selected))
assert(not registered.validate(subtitles, {}) and not registered.validate(subtitles, {1}))
local returned, active = registered.run(subtitles, selected, 3)
assert(returned == selected and active == 2)
assert(rows[2].text == "첫 선택 줄 [Lua ARM64]")
assert(rows[2].start_time == 1000 and rows[2].end_time == 2000 and rows[2].style == "Default")
assert(rows[1].text == "metadata" and rows[3].text == "다른 선택 줄")
assert(writes == 1 and undo_count == 1 and last_log:find("RESULT=PASS CODE=0", 1, true))
print("PASS macro callback: first selected only, copy/writeback, timing/style retained, undo=1")

local loaded, preload = package.loaded.lpeg, package.preload.lpeg
package.loaded.lpeg = nil
package.preload.lpeg = function() error("injected missing lpeg", 0) end
local ok = pcall(registered.run, subtitles, selected, 3)
package.loaded.lpeg, package.preload.lpeg = loaded, preload
assert(not ok and last_log:find("RESULT=FAIL CODE=1", 1, true))
assert(rows[2].text == "첫 선택 줄 [Lua ARM64]" and writes == 1 and undo_count == 1)
print("PASS injected missing native module: reported failure, no subtitle writes or undo")

ok = pcall(registered.run, subtitles, {}, 3)
assert(not ok and last_log:find("reason=INVALID_SELECTION", 1, true))
assert(writes == 1 and undo_count == 1)
print("PASS empty selection: no subtitle writes or undo")
print("DRIVER RESULT=PASS CODE=0")
