using System;
using System.Collections.Generic;
using System.IO;
using GZCTF.Services.Awdp;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace GZCTF.Test;

public class AwdpQueueTest
{
    [Fact]
    public void DefaultsToDisabled()
    {
        var queue = new AwdpQueue(new ConfigurationBuilder().Build());
        Assert.False(queue.IsEnabled(1, 2));
    }

    [Fact]
    public void QueuesServerBoundIdentityAndLimitsDuplicates()
    {
        var root = Path.Combine(Path.GetTempPath(), "awdp-test-" + Guid.NewGuid());
        try
        {
            var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Awdp:Enabled"] = "true", ["Awdp:Root"] = root,
                ["Awdp:Challenges:1:2"] = "ticket-attachments"
            }).Build();
            var queue = new AwdpQueue(configuration);
            var result = queue.Enqueue(1, 2, 3, "patch"u8.ToArray());
            Assert.Single(queue.List(1, 2, 3));
            Assert.Empty(queue.List(1, 2, 4));
            Assert.True(File.Exists(Path.Combine(root, "queue", "pending", result.Id + ".json")));
            Assert.Throws<AwdpQueueLimitException>(() => queue.Enqueue(1, 2, 3, "patch"u8.ToArray()));
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }
}
