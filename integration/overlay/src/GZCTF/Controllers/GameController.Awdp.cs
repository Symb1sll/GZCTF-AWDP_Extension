using System.Text;
using GZCTF.Middlewares;
using GZCTF.Services.Awdp;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace GZCTF.Controllers;

public partial class GameController
{
    [RequireUser]
    [HttpGet("{id:int}/Challenges/{challengeId:int}/Patches")]
    public async Task<IActionResult> GetPatches(int id, int challengeId,
        [FromServices] AwdpLedger queue, CancellationToken token)
    {
        var context = await GetContextInfo(id, challengeId, denyAfterEnded: false, token: token);
        if (context.Result is not null) return context.Result;
        if (!context.Challenge!.IsEnabled) return NotFound();
        if (!queue.IsEnabled(id, challengeId)) return Ok(new { enabled = false });
        return Ok(new { enabled = true, fixScore = queue.Points(id, challengeId), submissions = await queue.List(id, challengeId, context.Participation!.Id, token) });
    }

    [RequireUser]
    [HttpPost("{id:int}/Challenges/{challengeId:int}/Patches")]
    [EnableRateLimiting(nameof(RateLimiter.LimitPolicy.Submit))]
    [RequestSizeLimit(512 * 1024)]
    public async Task<IActionResult> SubmitPatch(int id, int challengeId,
        [FromServices] AwdpLedger queue, CancellationToken token)
    {
        // Require a non-simple same-origin browser request. Do not enable cross-origin CORS here.
        if (Request.Headers["X-AWDP-Request"] != "patch" ||
            Request.Headers["Sec-Fetch-Site"] == "cross-site") return StatusCode(403);
        var context = await GetContextInfo(id, challengeId, token: token);
        if (context.Result is not null) return context.Result;
        if (!context.Challenge!.IsEnabled || !queue.IsEnabled(id, challengeId)) return NotFound();
        if (context.Game!.EndTimeUtc <= DateTimeOffset.UtcNow)
            return BadRequest(new { error = "比赛已结束，不接受计分补丁" });
        if (!string.Equals(Request.ContentType, "text/x-diff", StringComparison.OrdinalIgnoreCase))
            return StatusCode(415);
        using var buffer = new MemoryStream();
        var chunk = new byte[8192];
        int count;
        while ((count = await Request.Body.ReadAsync(chunk, token)) > 0)
        {
            if (buffer.Length + count > 512 * 1024) return StatusCode(413);
            await buffer.WriteAsync(chunk.AsMemory(0, count), token);
        }
        var blob = buffer.ToArray();
        try
        {
            var text = new UTF8Encoding(false, true).GetString(blob);
            if (blob.Length == 0 || text.Contains('\0') || !text.Contains("--- ") || !text.Contains("+++ "))
                return BadRequest(new { error = "需要UTF-8 unified diff补丁" });
        }
        catch (DecoderFallbackException) { return BadRequest(new { error = "补丁不是有效UTF-8" }); }
        try
        {
            var record = await queue.Enqueue(id, challengeId, context.Participation!.Id, blob, token);
            return Accepted(new { record.Id, record.Status });
        }
        catch (AwdpQueueLimitException)
        {
            return StatusCode(429, new { error = "提交过快或已有3个待判任务" });
        }
        catch (AwdpAdmissionException)
        {
            return BadRequest(new { error = "比赛、题目或参赛状态已变化，请刷新后重试" });
        }
    }
}
