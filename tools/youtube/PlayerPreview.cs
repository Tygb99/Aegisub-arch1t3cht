using System.Diagnostics;
using System.Net.WebSockets;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Security.Cryptography;

static class PlayerPreview
{
    static Dictionary<string, string> Query(Uri uri) => uri.Query.TrimStart('?').Split('&')
        .Select(p => p.Split('=', 2)).Where(p => p.Length == 2)
        .GroupBy(p => p[0]).ToDictionary(g => g.Key, g => Uri.UnescapeDataString(g.Last()[1]));

    public static async Task Run(string[] args)
    {
        var url = new Uri(args[0]);
        if (url.Scheme != "https" || url.Host is not ("www.youtube.com" or "youtube.com") ||
            url.AbsolutePath != "/watch" || !Query(url).TryGetValue("v", out var video) ||
            !Regex.IsMatch(video, "^[A-Za-z0-9_-]{11}$"))
            throw new ArgumentException("https://www.youtube.com/watch?v=… 형식의 영상 URL을 입력하세요.");
        if (!Regex.IsMatch(args[2], "^[a-zA-Z0-9-]{2,20}$"))
            throw new ArgumentException("기존 자막 트랙의 언어 코드(예: en, ko)를 입력하세요.");
        var session = Path.GetFullPath(args[3]);
        var ytt = Path.GetFullPath(args[1]);
        Directory.CreateDirectory(session);
        var profile = Path.Combine(session, "browser-" + Guid.NewGuid().ToString("N"));
        var executable = FindBrowser();
        var start = new ProcessStartInfo(executable)
            { UseShellExecute = false, RedirectStandardError = true, RedirectStandardOutput = true };
        foreach (var argument in new[] { "--user-data-dir=" + profile, "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check", "about:blank" })
            start.ArgumentList.Add(argument);
        using var browser = Process.Start(start) ?? throw new IOException("Chrome 또는 Edge를 시작할 수 없습니다.");
        browser.BeginErrorReadLine(); browser.BeginOutputReadLine();
        try
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            var portFile = Path.Combine(profile, "DevToolsActivePort");
            var port = await ReadDevToolsPort(portFile, timeout.Token);
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
            using var tabs = JsonDocument.Parse(await http.GetStringAsync($"http://127.0.0.1:{port}/json/list", timeout.Token));
            var page = tabs.RootElement.EnumerateArray().First(t => t.GetProperty("type").GetString() == "page");
            using var socket = new ClientWebSocket();
            await socket.ConnectAsync(new Uri(page.GetProperty("webSocketDebuggerUrl").GetString()!), timeout.Token);
            using var receiveStop = new CancellationTokenSource();
            Task<JsonDocument>? receive = null;
            try
            {
                using var protocolLog = new StreamWriter(Path.Combine(session, "protocol.log")) { AutoFlush = true };
                var cdp = new CdpConnection(socket, protocolLog);
                var deliveries = new Dictionary<int, string>();
                await cdp.Send("Network.enable", new { });
                await cdp.Send("Fetch.enable", new { patterns = new[] {
                    new { urlPattern = "https://www.youtube.com/api/timedtext*", requestStage = "Request" } } });
                await cdp.Send("Page.navigate", new { url = url.AbsoluteUri });
                var status = Path.Combine(session, "status.txt");
                await File.WriteAllTextAsync(status, "대기: 선택한 언어의 기존 CC 트랙을 켜세요. 아직 로컬 자막이 적용되지 않았습니다.");
                receive = cdp.Receive(receiveStop.Token);
                while (!browser.HasExited && !File.Exists(Path.Combine(session, "stop")))
                {
                    cdp.CheckDeadlines();
                    if (await Task.WhenAny(receive, Task.Delay(250)) != receive) continue;
                    using var message = await receive;
                    var root = message.RootElement;
                    var acknowledged = cdp.Accept(root);
                    if (acknowledged == "Fetch.fulfillRequest" && deliveries.Remove(root.GetProperty("id").GetInt32(), out var hash))
                        await File.WriteAllTextAsync(status, $"SHA256 {hash}\n현재 YTT 응답 대체 확인 · {DateTime.Now:HH:mm:ss}\n표시 결과를 플레이어에서 확인하세요. 변경 후 CC를 껐다 켜세요.");
                    if (root.TryGetProperty("result", out var result) && result.TryGetProperty("errorText", out var navigationError))
                        await File.WriteAllTextAsync(status, "영상 열기 실패: " + navigationError.GetString());
                    if (root.TryGetProperty("error", out var error))
                        throw new IOException("브라우저 연결 오류: " + error.GetProperty("message").GetString());
                    if (root.TryGetProperty("method", out var method) && method.GetString() == "Network.loadingFailed")
                    {
                        var failed = root.GetProperty("params");
                        var type = failed.GetProperty("type").GetString();
                        await protocolLog.WriteLineAsync($"{DateTime.UtcNow:O} network {type} {failed.GetProperty("errorText").GetString()}");
                        if (type is "Document" or "Media")
                            await File.WriteAllTextAsync(status, "브라우저 영상/페이지 네트워크 오류: " + failed.GetProperty("errorText").GetString());
                    }
                    if (root.TryGetProperty("method", out method) && method.GetString() == "Fetch.requestPaused")
                    {
                        var data = root.GetProperty("params");
                        var requestId = data.GetProperty("requestId").GetString();
                        var request = new Uri(data.GetProperty("request").GetProperty("url").GetString()!);
                        var query = Query(request);
                        if (request.Host == "www.youtube.com" && request.AbsolutePath == "/api/timedtext" &&
                            query.GetValueOrDefault("v") == video && query.GetValueOrDefault("lang") == args[2] &&
                            !query.ContainsKey("tlang") && !query.ContainsKey("kind") && File.Exists(ytt))
                        {
                            var bytes = await File.ReadAllBytesAsync(ytt);
                            var command = await cdp.Send("Fetch.fulfillRequest", new { requestId, responseCode = 200,
                                responseHeaders = new[] { new { name = "Content-Type", value = "text/xml; charset=utf-8" },
                                    new { name = "Cache-Control", value = "no-store" },
                                    new { name = "Access-Control-Allow-Origin", value = "https://www.youtube.com" } },
                                body = Convert.ToBase64String(bytes) });
                            deliveries.Add(command, Convert.ToHexString(SHA256.HashData(bytes)));
                        }
                        else await cdp.Send("Fetch.continueRequest", new { requestId });
                    }
                    receive = cdp.Receive(receiveStop.Token);
                }
            }
            finally
            {
                receiveStop.Cancel();
                socket.Abort();
                if (receive != null)
                {
                    try { using var ignored = await receive; }
                    catch (Exception error) when (error is OperationCanceledException or WebSocketException or IOException) { }
                }
            }
        }
        finally
        {
            try
            {
                if (!browser.HasExited) browser.Kill(true);
            }
            catch (InvalidOperationException) { }
            await browser.WaitForExitAsync();
            await DeleteProfile(profile);
        }
    }

    static async Task<int> ReadDevToolsPort(string portFile, CancellationToken cancellationToken)
    {
        while (true)
        {
            try
            {
                if (File.Exists(portFile))
                {
                    var lines = await File.ReadAllLinesAsync(portFile, cancellationToken);
                    if (lines.Length > 0 && int.TryParse(lines[0], out var port)) return port;
                }
            }
            catch (IOException) { }
            await Task.Delay(100, cancellationToken);
        }
    }

    static string FindBrowser()
    {
        if (Environment.GetEnvironmentVariable("AEGISUB_YOUTUBE_CHROME") is { Length: > 0 } configured)
            return configured;
        if (OperatingSystem.IsMacOS())
            return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("실제 플레이어는 macOS와 Windows에서 Chrome 또는 Edge를 사용합니다.");

        var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        var programFilesX86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
        var localData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var candidates = new[] {
            Path.Combine(programFiles, "Google", "Chrome", "Application", "chrome.exe"),
            Path.Combine(programFilesX86, "Google", "Chrome", "Application", "chrome.exe"),
            Path.Combine(localData, "Google", "Chrome", "Application", "chrome.exe"),
            Path.Combine(programFiles, "Microsoft", "Edge", "Application", "msedge.exe"),
            Path.Combine(programFilesX86, "Microsoft", "Edge", "Application", "msedge.exe"),
            Path.Combine(localData, "Microsoft", "Edge", "Application", "msedge.exe")
        };
        return candidates.FirstOrDefault(File.Exists)
            ?? throw new FileNotFoundException("Google Chrome 또는 Microsoft Edge를 찾을 수 없습니다. AEGISUB_YOUTUBE_CHROME에 실행 파일 경로를 지정하세요.");
    }

    static async Task DeleteProfile(string profile)
    {
        for (var attempt = 0; Directory.Exists(profile); attempt++)
        {
            try
            {
                Directory.Delete(profile, true);
            }
            catch (Exception error) when (attempt < 9 && error is IOException or UnauthorizedAccessException)
            {
                await Task.Delay(100 * (attempt + 1));
            }
        }
    }
}
