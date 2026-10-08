using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;

namespace GZCTF.Services.Awdp;

public sealed class AwdpLedger(AppDbContext db, IConfiguration config)
{
    public string Root => config["Awdp:Root"] ?? throw new InvalidOperationException("Missing Awdp:Root");
    public string? Mapping(int game, int challenge) => config[$"Awdp:Challenges:{game}:{challenge}"];
    public bool IsEnabled(int game, int challenge) => config.GetValue<bool>("Awdp:Enabled") &&
        Mapping(game, challenge) is { } value && Regex.IsMatch(value, "^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$");
    public int Points(int game, int challenge) => Math.Clamp(config.GetValue<int?>($"Awdp:Scores:{game}:{challenge}") ?? 100, 0, 100000);

    public async Task<object[]> List(int game, int challenge, int participant, CancellationToken token) =>
        await db.AwdpSubmissions.AsNoTracking()
            .Where(x => x.GameId == game && x.ChallengeId == challenge && x.ParticipationId == participant)
            .OrderByDescending(x => x.CreatedAt).Take(50)
            .Select(x => (object)new { x.Id, x.CreatedAt, x.Status, x.Message, score = x.Status == "passed" ? x.FixScore : 0 })
            .ToArrayAsync(token);

    public async Task<AwdpSubmission> Enqueue(int game, int challenge, int participant, byte[] patch, CancellationToken token)
    {
        if (!IsEnabled(game, challenge)) throw new AwdpAdmissionException();
        await using var transaction = await db.Database.BeginTransactionAsync(token);
        // Serialize admission per participation, including multiple web processes.
        await db.Database.ExecuteSqlInterpolatedAsync($"SELECT pg_advisory_xact_lock(170901, {participant})", token);
        var now = DateTimeOffset.UtcNow;
        if (!await db.Participations.AnyAsync(x => x.Id == participant && x.GameId == game && x.Status == ParticipationStatus.Accepted, token) ||
            !await db.GameChallenges.AnyAsync(x => x.Id == challenge && x.GameId == game && x.IsEnabled, token) ||
            !await db.Games.AnyAsync(x => x.Id == game && x.StartTimeUtc <= now && x.EndTimeUtc > now, token))
            throw new AwdpAdmissionException();
        var submissions = db.AwdpSubmissions.Where(x => x.ParticipationId == participant && x.GameId == game);
        if (await submissions.AnyAsync(x => x.CreatedAt > now.AddSeconds(-5), token) ||
            await submissions.CountAsync(x => x.Status == "queued" || x.Status == "running", token) >= 3)
            throw new AwdpQueueLimitException();
        var record = new AwdpSubmission
        {
            Id = Guid.NewGuid(), GameId = game, ChallengeId = challenge, ParticipationId = participant,
            RunnerChallenge = Mapping(game, challenge)!, Patch = patch,
            PatchSha256 = Convert.ToHexStringLower(SHA256.HashData(patch)),
            CreatedAt = now, FixScore = Points(game, challenge)
        };
        db.AwdpSubmissions.Add(record);
        await db.SaveChangesAsync(token);
        await transaction.CommitAsync(token);
        // Durable database outbox: background worker publishes/retries independently.
        return record;
    }

    public static bool MatchesResult(AwdpSubmission record, JsonElement result) =>
        result.TryGetProperty("submission_id", out var id) && id.GetString() == record.Id.ToString() &&
        result.TryGetProperty("team_id", out var team) && team.GetString() == $"g{record.GameId}-p{record.ParticipationId}" &&
        result.TryGetProperty("challenge_id", out var challenge) && challenge.GetString() == record.RunnerChallenge &&
        result.TryGetProperty("patch_sha256", out var hash) && hash.GetString() == record.PatchSha256;

    public static void AtomicWrite(string path, byte[] bytes)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { stream.Write(bytes); stream.Flush(true); }
            if (!OperatingSystem.IsWindows()) File.SetUnixFileMode(temp,
                UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.GroupRead | UnixFileMode.GroupWrite);
            File.Move(temp, path, true);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
}

public sealed class AwdpAdmissionException : Exception;
