using System.ComponentModel.DataAnnotations;
using Microsoft.EntityFrameworkCore;

namespace GZCTF.Models.Data;

[Index(nameof(GameId), nameof(ChallengeId), nameof(ParticipationId), nameof(CreatedAt))]
public class AwdpSubmission
{
    public Guid Id { get; set; }
    public int GameId { get; set; }
    public Game Game { get; set; } = null!;
    public int ChallengeId { get; set; }
    public GameChallenge Challenge { get; set; } = null!;
    public int ParticipationId { get; set; }
    public Participation Participation { get; set; } = null!;
    [MaxLength(64)] public string RunnerChallenge { get; set; } = "";
    [MaxLength(64)] public string PatchSha256 { get; set; } = "";
    public byte[] Patch { get; set; } = [];
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset? FinishedAt { get; set; }
    [MaxLength(16)] public string Status { get; set; } = "queued";
    [MaxLength(1000)] public string Message { get; set; } = "";
    public int FixScore { get; set; }
}
