using System.Text.Json;
using System.Text.RegularExpressions;

namespace GZCTF.Services.Awdp;

public sealed class AwdpQueueLimitException : Exception { }

// Single-process development adapter. Records remain on disk; not a scoring ledger.
// The results mount must be read-only to the web application and writable only by the runner.
public sealed class AwdpQueue(IConfiguration configuration)
{
    private readonly object gate = new();
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private string Root => configuration["Awdp:Root"]
        ?? throw new InvalidOperationException("Awdp:Root is not configured");
    private string? Mapping(int game, int challenge) => configuration[$"Awdp:Challenges:{game}:{challenge}"];
    public bool IsEnabled(int game, int challenge) =>
        configuration.GetValue<bool>("Awdp:Enabled") &&
        Mapping(game, challenge) is { } value && Regex.IsMatch(value, "^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$");

    private IEnumerable<PatchRecord> Records(int game, int challenge, int participant)
    {
        var directory = Path.Combine(Root, "records", $"{game}-{challenge}-{participant}");
        if (!Directory.Exists(directory)) yield break;
        foreach (var path in Directory.EnumerateFiles(directory, "*.json"))
        {
            var record = JsonSerializer.Deserialize<PatchRecord>(File.ReadAllText(path), Json)
                ?? throw new InvalidDataException("Invalid AWDP record");
            yield return record;
        }
    }

    private PatchRecord WithResult(PatchRecord record)
    {
        var path = Path.Combine(Root, "queue", "results", record.Id + ".json");
        if (!File.Exists(path))
            return record with { Status = File.Exists(Path.Combine(Root, "queue", "running", record.Id + ".json")) ? "running" : record.Status };
        if (new FileInfo(path).Length > 128 * 1024) throw new InvalidDataException("Oversized result");
        using var result = JsonDocument.Parse(File.ReadAllText(path));
        var value = result.RootElement;
        if (value.GetProperty("submission_id").GetString() != record.Id)
            throw new InvalidDataException("Mismatched submission result");
        var status = value.GetProperty("status").GetString();
        if (status is not ("passed" or "failed" or "error" or "timeout"))
            throw new InvalidDataException("Invalid result status");
        // Do not expose raw runner logs or trust its numeric score as GZCTF points.
        var message = value.TryGetProperty("message", out var m) ? m.GetString() ?? "" : "";
        return record with { Status = status, Message = message[..Math.Min(message.Length, 1000)] };
    }

    public PatchRecord[] List(int game, int challenge, int participant)
    {
        lock (gate)
            return Records(game, challenge, participant).OrderByDescending(x => x.CreatedAt)
                .Take(50).Select(WithResult).ToArray();
    }

    public PatchRecord Enqueue(int game, int challenge, int participant, byte[] patch)
    {
        lock (gate)
        {
            if (!IsEnabled(game, challenge)) throw new InvalidOperationException("AWDP disabled");
            var records = Records(game, challenge, participant).Select(WithResult).ToArray();
            var now = DateTimeOffset.UtcNow;
            if (records.Any(x => now - x.CreatedAt < TimeSpan.FromSeconds(5)) ||
                records.Count(x => x.Status is "queued" or "running") >= 3)
                throw new AwdpQueueLimitException();
            var record = new PatchRecord(Guid.NewGuid().ToString(), now, "queued", "");
            var recordPath = Path.Combine(Root, "records", $"{game}-{challenge}-{participant}", record.Id + ".json");
            AtomicWrite(Path.Combine(Root, "data", "submissions", record.Id + ".patch"), patch);
            AtomicWrite(recordPath, JsonSerializer.SerializeToUtf8Bytes(record, Json));
            try
            {
                AtomicWrite(Path.Combine(Root, "queue", "pending", record.Id + ".json"),
                    JsonSerializer.SerializeToUtf8Bytes(new
                    {
                        schema_version = 1, submission_id = record.Id,
                        team_id = $"g{game}-p{participant}", challenge_id = Mapping(game, challenge),
                        created_at = now.ToString("O")
                    }));
            }
            catch
            {
                AtomicWrite(recordPath, JsonSerializer.SerializeToUtf8Bytes(
                    record with { Status = "error", Message = "任务发布失败" }, Json));
                throw;
            }
            return record;
        }
    }

    private static void AtomicWrite(string path, byte[] content)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                stream.Write(content);
                stream.Flush(true);
            }
            if (!OperatingSystem.IsWindows())
                File.SetUnixFileMode(temp, UnixFileMode.UserRead | UnixFileMode.UserWrite |
                    UnixFileMode.GroupRead | UnixFileMode.GroupWrite);
            File.Move(temp, path, true);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
}

public sealed record PatchRecord(string Id, DateTimeOffset CreatedAt, string Status, string Message);
