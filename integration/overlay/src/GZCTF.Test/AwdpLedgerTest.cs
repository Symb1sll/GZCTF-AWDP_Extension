using System;
using System.Linq;
using System.Text.Json;
using GZCTF.Models.Data;
using GZCTF.Services.Awdp;
using Xunit;

namespace GZCTF.Test;

public class AwdpLedgerTest
{
    [Theory]
    [InlineData("team_id", "g1-p9")]
    [InlineData("team_id", "g2-p3")]
    [InlineData("challenge_id", "other")]
    [InlineData("patch_sha256", "different")]
    [InlineData("submission_id", "00000000-0000-0000-0000-000000000000")]
    public void RejectsReboundResults(string field, string value)
    {
        var record = new AwdpSubmission { Id = Guid.NewGuid(), GameId = 1, ParticipationId = 3,
            RunnerChallenge = "ticket", PatchSha256 = "hash" };
        var fields = new System.Collections.Generic.Dictionary<string, string> {
            ["submission_id"] = record.Id.ToString(), ["team_id"] = "g1-p3",
            ["challenge_id"] = "ticket", ["patch_sha256"] = "hash" };
        using var valid = JsonDocument.Parse(JsonSerializer.Serialize(fields));
        Assert.True(AwdpLedger.MatchesResult(record, valid.RootElement));
        fields[field] = value;
        using var invalid = JsonDocument.Parse(JsonSerializer.Serialize(fields));
        Assert.False(AwdpLedger.MatchesResult(record, invalid.RootElement));
    }

    [Fact]
    public void RepeatedPassDoesNotAccumulateOrMixParticipantsAndChallenges()
    {
        var now = DateTimeOffset.UtcNow;
        var awards = new[] { new AwdpAward(1, 2, 100, now), new AwdpAward(1, 2, 100, now.AddMinutes(1)),
            new AwdpAward(2, 2, 100, now), new AwdpAward(1, 3, 50, now) };
        var best = AwdpScoring.BestPerChallenge(awards).ToArray();
        Assert.Equal(3, best.Length);
        Assert.Equal(150, best.Where(x => x.ParticipationId == 1).Sum(x => x.FixScore));
        Assert.Equal(now, best.Single(x => x.ParticipationId == 1 && x.ChallengeId == 2).CreatedAt);
    }
}
