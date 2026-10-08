using GZCTF.Services.Awdp;
using System.Text.Json;

var root = Path.Combine(Path.GetTempPath(), "awdp-validation-" + Guid.NewGuid());
var checks = 0;
void Check(bool success, string name)
{
    if (!success) throw new Exception("FAIL " + name);
    Console.WriteLine("PASS " + name);
    checks++;
}
try
{
    Check(!new AwdpQueue(new ConfigurationBuilder().Build()).IsEnabled(1, 2), "disabled by default");
    var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["Awdp:Enabled"] = "true", ["Awdp:Root"] = root,
        ["Awdp:Challenges:1:2"] = "ticket-attachments"
    }).Build();
    var queue = new AwdpQueue(config);
    Check(queue.IsEnabled(1, 2) && !queue.IsEnabled(1, 3), "explicit challenge mapping");
    var record = queue.Enqueue(1, 2, 3, "--- a/src/app.py\n+++ b/src/app.py\n"u8.ToArray());
    Check(queue.List(1, 2, 3).Length == 1, "record persisted");
    Check(queue.List(1, 2, 4).Length == 0, "other participant cannot list record");
    using var job = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "queue", "pending", record.Id + ".json")));
    Check(job.RootElement.GetProperty("team_id").GetString() == "g1-p3", "server-bound runner identity");
    var limited = false;
    try { queue.Enqueue(1, 2, 3, "patch"u8.ToArray()); }
    catch (AwdpQueueLimitException) { limited = true; }
    Check(limited, "immediate duplicate rate limited");
    Directory.CreateDirectory(Path.Combine(root, "queue", "results"));
    var resultPath = Path.Combine(root, "queue", "results", record.Id + ".json");
    File.WriteAllText(resultPath, JsonSerializer.Serialize(new { submission_id = record.Id, status = "passed", message = "ok", score = 999999 }));
    Check(queue.List(1, 2, 3)[0].Status == "passed", "result read without awarding numeric score");
    File.WriteAllText(resultPath, JsonSerializer.Serialize(new { submission_id = Guid.NewGuid().ToString(), status = "passed" }));
    var rejected = false;
    try { queue.List(1, 2, 3); }
    catch (InvalidDataException) { rejected = true; }
    Check(rejected, "mismatched result rejected");
    Console.WriteLine($"SUMMARY {checks} checks passed");
}
finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
