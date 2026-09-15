using System.Net.WebSockets;
using System.Text.Json;

sealed class CdpConnection(ClientWebSocket socket, TextWriter log)
{
    int nextId;
    readonly Dictionary<int, (string Method, DateTime Sent)> pending = [];
    public async Task<int> Send(string method, object parameters, CancellationToken cancellationToken = default)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(new { id = ++nextId, method, @params = parameters });
        pending.Add(nextId, (method, DateTime.UtcNow));
        await log.WriteLineAsync($"{DateTime.UtcNow:O} send {nextId} {method}");
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(15));
        await socket.SendAsync(bytes.AsMemory(), WebSocketMessageType.Text, true, timeout.Token);
        return nextId;
    }

    public string? Accept(JsonElement message)
    {
        if (!message.TryGetProperty("id", out var id) || !pending.Remove(id.GetInt32(), out var command)) return null;
        log.WriteLine($"{DateTime.UtcNow:O} reply {id} {command.Method}");
        if (message.TryGetProperty("error", out var error))
            throw new IOException(command.Method + ": " + error.GetProperty("message").GetString());
        return command.Method;
    }

    public void CheckDeadlines()
    {
        foreach (var command in pending.Values)
            if (DateTime.UtcNow - command.Sent > TimeSpan.FromSeconds(command.Method == "Page.navigate" ? 60 : 15))
                throw new IOException("브라우저 응답 시간 초과: " + command.Method);
    }
    public async Task<JsonDocument> Receive(CancellationToken cancellationToken = default)
    {
        using var output = new MemoryStream();
        var buffer = new byte[65536];
        ValueWebSocketReceiveResult result;
        do
        {
            result = await socket.ReceiveAsync(buffer.AsMemory(), cancellationToken);
            if (result.MessageType == WebSocketMessageType.Close) throw new IOException("브라우저가 닫혔습니다.");
            output.Write(buffer, 0, result.Count);
        } while (!result.EndOfMessage);
        return JsonDocument.Parse(output.ToArray());
    }
}
