using System.Text.Json;
using GZCTF.Services.Cache;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Distributed;

namespace GZCTF.Services.Awdp;

public sealed class AwdpWorker(IServiceScopeFactory scopes, IConfiguration config, ILogger<AwdpWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!config.GetValue<bool>("Awdp:Enabled")) return;
        while (!stoppingToken.IsCancellationRequested)
        {
            try { await Tick(stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception e) { logger.LogError(e, "AWDP dispatcher failed; retrying"); }
            await Task.Delay(TimeSpan.FromSeconds(2), stoppingToken);
        }
    }

    private async Task Tick(CancellationToken token)
    {
        await using var scope = scopes.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var ledger = scope.ServiceProvider.GetRequiredService<AwdpLedger>();
        await using var transaction = await db.Database.BeginTransactionAsync(token);
        await db.Database.ExecuteSqlRawAsync("SELECT pg_advisory_xact_lock(170901, -1)", token);
        var records = await db.AwdpSubmissions.Where(x => x.Status == "queued" || x.Status == "running")
            .OrderBy(x => x.CreatedAt).Take(100).ToArrayAsync(token);
        var changed = new HashSet<int>();
        foreach (var record in records)
        {
            try
            {
            var id = record.Id.ToString();
            var resultPath = Path.Combine(ledger.Root, "queue", "results", id + ".json");
            if (File.Exists(resultPath))
            {
                if (new FileInfo(resultPath).Length > 128 * 1024) throw new InvalidDataException("Oversized AWDP result");
                using var result = JsonDocument.Parse(await File.ReadAllTextAsync(resultPath, token));
                var value = result.RootElement;
                if (!AwdpLedger.MatchesResult(record, value))
                { record.Status = "error"; record.Message = "判题结果身份或补丁摘要不匹配"; }
                else
                {
                    var status = value.GetProperty("status").GetString();
                    record.Status = status is "passed" or "failed" or "timeout" or "error" ? status : "error";
                    // Fixed messages; do not display user-controlled target logs or runner scores.
                    record.Message = record.Status switch
                    {
                        "passed" => "功能与漏洞回归通过", "failed" => "功能或漏洞回归未通过",
                        "timeout" => "判题超时", _ => "判题执行错误"
                    };
                }
                record.FinishedAt = DateTimeOffset.UtcNow;
                changed.Add(record.GameId);
                continue;
            }
            var running = Path.Combine(ledger.Root, "queue", "running", id + ".json");
            var pending = Path.Combine(ledger.Root, "queue", "pending", id + ".json");
            if (File.Exists(running)) { record.Status = "running"; continue; }
            if (File.Exists(pending)) continue;
            if (File.Exists(Path.Combine(ledger.Root, "queue", "archive", id + ".json")))
            { record.Status = "error"; record.Message = "判题归档缺少结果"; record.FinishedAt = DateTimeOffset.UtcNow; continue; }
            AwdpLedger.AtomicWrite(Path.Combine(ledger.Root, "data", "submissions", id + ".patch"), record.Patch);
            AwdpLedger.AtomicWrite(pending, JsonSerializer.SerializeToUtf8Bytes(new
            {
                schema_version = 1, submission_id = id, team_id = $"g{record.GameId}-p{record.ParticipationId}",
                challenge_id = record.RunnerChallenge, patch_sha256 = record.PatchSha256,
                created_at = record.CreatedAt.ToString("O")
            }));
            }
            catch (Exception e) when (e is JsonException or InvalidDataException or KeyNotFoundException or InvalidOperationException)
            {
                record.Status = "error";
                record.Message = "判题结果格式无效";
                record.FinishedAt = DateTimeOffset.UtcNow;
                logger.LogWarning(e, "Invalid AWDP result for {SubmissionId}", record.Id);
            }
        }
        await db.SaveChangesAsync(token);
        await transaction.CommitAsync(token);
        foreach (var game in changed)
        {
            await scope.ServiceProvider.GetRequiredService<IDistributedCache>().RemoveAsync(CacheKey.ScoreBoard(game), token);
            await scope.ServiceProvider.GetRequiredService<CacheHelper>().FlushScoreboardCache(game, token);
        }
    }
}
