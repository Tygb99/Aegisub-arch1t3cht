#!/usr/bin/env ruby
require 'open3'
require 'json'
require 'digest'
require 'tmpdir'
require 'fileutils'
require 'rexml/document'

root = File.expand_path('..', __dir__)
Dir.chdir(root)
helper = File.expand_path(ARGV.fetch(0, 'build-youtube/aegisub-youtube'))
output = Dir.mktmpdir('youtube-회귀 결과-', File.join(root, 'artifacts'))
upstream = File.join(root, '.deps/src/YTSubConverter-b186a40bc21e58a8c9651cf616cbb5e80425dfc6/YTSubConverter.Tests')
results = []
check = lambda do |name, &block|
  block.call
  results << {name: name, status: 'passed'}
  puts "PASS #{name}"
rescue StandardError => error
  results << {name: name, status: 'failed', error: error.message}
  warn "FAIL #{name}: #{error.message}"
end
assert = ->(condition, message) { raise message unless condition }
run = lambda do |*arguments|
  stdout, stderr, status = Open3.capture3({'DOTNET_ROOT' => nil, 'PATH' => '/usr/bin:/bin'}, helper, *arguments)
  raise "#{arguments.first}: #{stderr} #{stdout}" unless status.success?
  stdout
end
bytes = ->(path) { File.binread(path).delete_prefix("\xEF\xBB\xBF".b) }
convert = lambda do |name, input, options = nil|
  destination = File.join(output, name)
  arguments = ['preview', input, destination]
  arguments << options if options
  run.call(*arguments)
  destination
end
check.call('self-contained help') { assert.call(run.call('--help').include?('preview'), 'help missing') }
%w[Alignment BoldItalicUnderline Colors Fonts FaultTolerance NoDefaultScale Shadows Karaoke Fade Move Transform Ruby TextDirection].each do |name|
  check.call("upstream golden #{name}") do
    source = File.join(upstream, 'Ass/Files', name + '.ass')
    destination = convert.call(name, source, File.join(upstream, 'StyleOptions.xml'))
    assert.call(bytes.call(File.join(destination, 'result.ytt')) == bytes.call(File.join(upstream, 'Ass/Files', name + '.ytt')), 'YTT differs from pinned golden')
    assert.call(File.binread(source) == File.binread(File.join(destination, 'source.ass')), 'source changed')
  end
end
sample = File.join(root, 'tests/youtube-fixtures/한글 샘플.ass')
check.call('Korean paths, manifest, editable import, source preservation') do
  digest = Digest::SHA256.file(sample).hexdigest
  destination = convert.call('한글 출력', sample)
  manifest = JSON.parse(File.read(File.join(destination, 'manifest.json')))
  assert.call(manifest['yttSha256'].downcase == Digest::SHA256.file(File.join(destination, 'result.ytt')).hexdigest, 'hash mismatch')
  assert.call(manifest['inputEvents'] == 3 && manifest['expandedEvents'] > 3, 'effect expansion missing')
  imported = File.join(output, '역변환.ass')
  run.call('import', File.join(destination, 'result.ytt'), imported)
  assert.call(File.read(imported).include?('안녕하세요'), 'Korean import missing')
  assert.call(Digest::SHA256.file(sample).hexdigest == digest, 'input modified')
  _, _, status = Open3.capture3(helper, 'import', File.join(destination, 'result.ytt'), imported)
  assert.call(!status.success?, 'existing import output overwritten')
  _, _, status = Open3.capture3(helper, 'preview', sample, destination)
  assert.call(!status.success?, 'existing preview output overwritten')
end
header = File.read(sample).split('[Events]').first
event_header = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
ass = lambda do |name, text, custom_header = header|
  path = File.join(output, name + '.ass')
  File.write(path, custom_header + event_header + "Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,#{text}\n")
  path
end
check.call('standard and nonstandard scalar parentheses; position parser boundary') do
  standard = convert.call('standard', ass.call('standard', '{\\fs84\\c&H0000FF&\\pos(640,360)}X'))
  tolerated = convert.call('tolerated', ass.call('tolerated', '{\\fs(84)\\c(&H0000FF&)\\pos(640,360)}X'))
  invalid = convert.call('invalid-pos', ass.call('invalid-pos', '{\\fs84\\c&H0000FF&\\pos640,360}X'))
  assert.call(bytes.call(File.join(standard, 'result.ytt')) == bytes.call(File.join(tolerated, 'result.ytt')), 'parenthesized scalar behavior changed')
  assert.call(bytes.call(File.join(standard, 'result.ytt')) != bytes.call(File.join(invalid, 'result.ytt')), 'unparenthesized position unexpectedly accepted')
  xml = REXML::Document.new(File.read(File.join(standard, 'result.ytt')))
  assert.call(REXML::XPath.match(xml, '//pen').any? { |pen| pen.attributes['sz'] == '500' && pen.attributes['fc'] == '#FF0000' }, 'Default relative size/color mismatch')
  assert.call(REXML::XPath.match(xml, '//wp').any? { |position| position.attributes['ah'] == '50' && position.attributes['av'] == '50' }, 'position mismatch')
end
check.call('karaoke centiseconds and nonstandard parentheses') do
  native_header = header.sub('&H0000FFFF', '&HFF00FFFF').sub(',1,2,2,2,30,30,40,1', ',1,0,0,2,30,30,40,1')
  standard = convert.call('k25', ass.call('k25', '{\\pos(640,360)\\k25}Ka{\\k25}ra', native_header))
  nonstandard = convert.call('k-parentheses', ass.call('k-parentheses', '{\\pos(640,360)\\k(25)}Ka{\\k25}ra', native_header))
  xml = REXML::Document.new(File.read(File.join(standard, 'result.ytt')))
  assert.call(REXML::XPath.match(xml, '//s').any? { |span| span.text.to_s.include?('ra') && span.attributes['t'] == '250' }, 'k25 does not yield 250ms onset')
  assert.call(bytes.call(File.join(standard, 'result.ytt')) != bytes.call(File.join(nonstandard, 'result.ytt')), 'k parentheses unexpectedly equivalent')
end
check.call('output profile scale and coordinate offset') do
  input = ass.call('profile', '{\\pos(640,360)}X')
  options = File.join(output, 'profile.xml')
  File.write(options, '<StyleOptions><Output Scale="2" OffsetX="128" OffsetY="0" Mobile="false"/></StyleOptions>')
  destination = convert.call('profile-result', input, options)
  xml = REXML::Document.new(File.read(File.join(destination, 'result.ytt')))
  assert.call(REXML::XPath.match(xml, '//pen').any? { |p| p.attributes['sz'] == '500' }, 'scale missing')
  assert.call(REXML::XPath.match(xml, '//wp').any? { |p| p.attributes['ah'] == '60' }, 'offset missing')
end
check.call('mobile input collision preserves source; effects simplify') do
  directory = File.join(output, 'mobile')
  FileUtils.mkdir_p(directory)
  input = File.join(directory, 'mobile.input.ass')
  FileUtils.cp(sample, input)
  digest = Digest::SHA256.file(input).hexdigest
  options = File.join(output, 'mobile.xml')
  File.write(options, '<StyleOptions><Output Scale="1" Mobile="true"/></StyleOptions>')
  run.call('preview', input, directory, options)
  manifest = JSON.parse(File.read(File.join(directory, 'manifest.json')))
  assert.call(manifest['profile']['Mobile'] && manifest['expandedEvents'] == 3, 'mobile effects not simplified')
  assert.call(Digest::SHA256.file(input).hexdigest == digest, 'mobile source overwritten')
  assert.call(File.binread(input) == File.binread(File.join(directory, 'source.ass')), 'exported source modified')
end
check.call('malformed options fail before publishing YTT') do
  options = File.join(output, 'bad.xml')
  File.write(options, '<StyleOptions><broken>')
  destination = File.join(output, 'bad-options')
  _, _, status = Open3.capture3(helper, 'preview', sample, destination, options)
  assert.call(!status.success? && !File.exist?(File.join(destination, 'result.ytt')), 'invalid options accepted')
end
check.call('mobile drops drawing runs, preserves surrounding text and line breaks') do
  input = ass.call('mobile-drawing', '앞{\\p1}m 0 0 l 100 0{\\c&HFF&} l 100 100{\\p0}뒤{\\p2}m 1 2 l 3 4{\\p0}\\N끝')
  File.open(input, 'a') { |file| file.puts('Dialogue: 0,0:00:06.00,0:00:07.00,Default,,0,0,0,,{\\p1}m 50 50 l 60 60') }
  digest = Digest::SHA256.file(input).hexdigest
  options = File.join(output, 'mobile-drawing.xml')
  File.write(options, '<StyleOptions><Output Mobile="true"/></StyleOptions>')
  destination = convert.call('mobile-drawing-output', input, options)
  xml = REXML::Document.new(File.read(File.join(destination, 'result.ytt')))
  visible = REXML::XPath.match(xml, '//body/p//text()').map(&:value).join.gsub(/[\u200b\u00a0 ]/, '')
  assert.call(visible == "앞뒤\n끝", 'drawing coordinates leaked or visible text/line break lost')
  assert.call(Digest::SHA256.file(input).hexdigest == digest, 'drawing source changed')
end
alignment_xml = File.join(output, 'independent-alignment.ytt')
positions = (0..8).map { |ap| %(<wp id="#{ap}" ap="#{ap}" ah="25" av="75"/>) }.join
windows = (0..2).map { |ju| %(<ws id="#{ju}" ju="#{ju}"/>) }.join
paragraphs = (0..8).flat_map do |ap|
  (0..2).map do |ju|
    index = ap * 3 + ju
    %(<p t="#{1000 + index * 3000}" d="2000" wp="#{ap}" ws="#{ju}" p="0">A#{ap}J#{ju}\nLong line</p>)
  end
end.join
File.write(alignment_xml, %(<timedtext format="3"><head>#{positions}#{windows}<pen id="0" sz="100" fc="#FEFEFE" fo="254" bo="0"/></head><body>#{paragraphs}</body></timedtext>))
imported_alignment = File.join(output, 'independent-alignment.ass')
alignment_output = File.join(output, 'alignment-roundtrip')
check.call('independent alignment import and provenance') do
  _, stderr, status = Open3.capture3(helper, 'import', alignment_xml, imported_alignment)
  assert.call(status.success?, stderr)
  warnings = stderr.lines.map { |line| JSON.parse(line) }
  assert.call(warnings.select { |issue| issue['code'] == 'YTJU_VISUAL_ALIGNMENT' }.sum { |issue| issue.fetch('count') } == 18, 'editable import silently claims independent visual alignment')
  assert.call(stderr.bytesize < 4096, 'import warnings can fill the native process error pipe')
  run.call('preview', imported_alignment, alignment_output)
  manifest = JSON.parse(File.read(File.join(alignment_output, 'manifest.json')))
  assert.call(manifest['engine'] == 'b186a40bc21e58a8c9651cf616cbb5e80425dfc6', 'base revision changed')
  assert.call(manifest['enginePatch'] == 'c460cca9f5b37aa0e98e460007f7379df5732d05', 'upstream patch revision missing')
  assert.call(manifest['assAlignmentTag'] == 'ytju', 'ASS bridge metadata missing')
  assert.call(manifest['visualIndependentAlignmentPreserved'] == false, 'manifest claims unsupported visual alignment')
end
(0..8).each do |ap|
  (0..2).each do |ju|
    check.call("anchor #{ap} justification #{ju}: editable geometry and visual limitation") do
      marker = "A#{ap}J#{ju}"
      ass_text = File.read(imported_alignment)
      dialogue = ass_text.lines.find { |line| line.start_with?('Dialogue:') && line.include?(marker) }
      assert.call(dialogue && dialogue.include?("\\ytju#{ju}"), 'explicit justification lost in ASS')
      fields = dialogue.split(',', 10)
      style = ass_text.lines.find { |line| line.start_with?("Style: #{fields[3]},") }.split(',')
      anchor = fields[9][/\\an([1-9])/, 1] || style[18]
      assert.call(anchor.to_i == [7, 8, 9, 4, 5, 6, 1, 2, 3][ap], 'ASS anchor changed to match justification')
      xy = fields[9].match(/\\pos\(([-\d.]+),([-\d.]+)\)/)
      assert.call(xy && (xy[1].to_f - 332.8).abs < 0.01 && (xy[2].to_f - 532.8).abs < 0.01, 'YTT inset coordinate transform lost')
      xml = REXML::Document.new(File.read(File.join(alignment_output, 'result.ytt')))
      paragraph = REXML::XPath.match(xml, '//body/p').find { |p| p.to_s.include?(marker) }
      assert.call(paragraph, 'round-trip text missing')
      wp = REXML::XPath.first(xml, "//wp[@id='#{paragraph.attributes['wp']}']")
      ws = REXML::XPath.first(xml, "//ws[@id='#{paragraph.attributes['ws']}']")
      assert.call([wp.attributes['ap'], ws.attributes['ju'], wp.attributes['ah'], wp.attributes['av']] == [ap, ju, 25, 75].map(&:to_s), 'independent ap/ju or position collapsed')
      expected_start = 1000 + (ap * 3 + ju) * 3000
      actual_start = paragraph.attributes['t'].to_i
      actual_end = actual_start + paragraph.attributes['d'].to_i
      assert.call((actual_start - expected_start).abs <= 20 && (actual_end - expected_start - 2000).abs <= 20, 'round-trip timing moved beyond frame rounding')
      manifest = JSON.parse(File.read(File.join(alignment_output, 'manifest.json')))
      diagnostics = manifest.fetch('visualDiagnostics')
      diagnostic = diagnostics.find { |item| item['text'].include?(marker) }
      mismatch = ju != [0, 2, 1][ap % 3]
      assert.call(!diagnostic.nil? == mismatch, 'visual limitation detection does not match independent alignment')
      if mismatch
        assert.call(diagnostic['code'] == 'YTJU_VISUAL_ALIGNMENT' && diagnostic['justification'] == ju && diagnostic['action'] == 'verify-result-ytt-in-player', 'limitation lacks actionable metadata')
      end
    end
  end
end
check.call('missing ju falls back to anchor-derived justification') do
  input = File.join(output, 'derived-justification.ytt')
  File.write(input, '<timedtext format="3"><head><wp id="0" ap="8" ah="50" av="50"/><ws id="0"/><pen id="0" fc="#FEFEFE" fo="254"/></head><body><p t="1000" d="2000" wp="0" ws="0" p="0">fallback</p></body></timedtext>')
  imported = File.join(output, 'derived-justification.ass')
  run.call('import', input, imported)
  assert.call(!File.read(imported).include?('\\ytju'), 'missing ju became an explicit override')
  destination = convert.call('derived-justification-output', imported)
  xml = REXML::Document.new(File.read(File.join(destination, 'result.ytt')))
  p = REXML::XPath.match(xml, '//body/p').find { |item| item.to_s.include?('fallback') }
  ws = REXML::XPath.first(xml, "//ws[@id='#{p.attributes['ws']}']")
  assert.call(ws.attributes['ju'] == '1', 'right anchor no longer derives right justification')
  assert.call(JSON.parse(File.read(File.join(destination, 'manifest.json')))['visualDiagnostics'] == [], 'legacy alignment falsely warned')
end
check.call('invalid ytju fails before publishing YTT') do
  input = ass.call('invalid-ytju', '{\\ytju3}X')
  destination = File.join(output, 'invalid-ytju-output')
  _, _, status = Open3.capture3(helper, 'preview', input, destination)
  assert.call(!status.success? && !File.exist?(File.join(destination, 'result.ytt')), 'invalid justification accepted')
end
File.write(File.join(output, 'results.json'), JSON.pretty_generate({helper: helper, results: results}))
puts output
exit(results.all? { |result| result[:status] == 'passed' } ? 0 : 1)
