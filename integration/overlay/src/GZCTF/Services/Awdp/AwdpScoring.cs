namespace GZCTF.Services.Awdp;

public sealed record AwdpAward(int ParticipationId, int ChallengeId, int FixScore, DateTimeOffset CreatedAt);

public static class AwdpScoring
{
    // Input is already scoped to one game and accepted, enabled submissions by the repository.
    public static IEnumerable<AwdpAward> BestPerChallenge(IEnumerable<AwdpAward> awards) =>
        awards.GroupBy(x => (x.ParticipationId, x.ChallengeId))
            .Select(g => g.OrderByDescending(x => x.FixScore).ThenBy(x => x.CreatedAt).First());
}
