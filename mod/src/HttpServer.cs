using System.Net;
using System.Text;
using System.Text.Json;

namespace Sts2AiMod;

public class AiHttpServer : IDisposable
{
    private readonly HttpListener _listener = new();
    private readonly CancellationTokenSource _cts = new();
    private Task? _listenTask;
    private bool _running;

    public int Port { get; }

    public AiHttpServer(int port = 18888)
    {
        Port = port;
        _listener.Prefixes.Add($"http://127.0.0.1:{Port}/");
        _listener.Prefixes.Add($"http://localhost:{Port}/");
    }

    public void Start()
    {
        if (_running) return;
        _running = true;
        _listener.Start();
        _listenTask = Task.Run(() => ListenLoop(_cts.Token));
        ModLogger.Log($"HTTP server started on port {Port}");
    }

    private async Task ListenLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var ctxTask = _listener.GetContextAsync();
                var ctx = await ctxTask.WaitAsync(ct);
                _ = Task.Run(() => HandleRequest(ctx), ct);
            }
            catch { break; }
        }
    }

    private void HandleRequest(HttpListenerContext ctx)
    {
        try
        {
            var path = ctx.Request.Url?.AbsolutePath ?? "/";
            switch (path)
            {
                case "/state" when ctx.Request.HttpMethod == "GET":
                    HandleGetState(ctx); break;
                case "/status" when ctx.Request.HttpMethod == "GET":
                    HandleGetStatus(ctx); break;
                case "/decision" when ctx.Request.HttpMethod == "POST":
                    HandlePostDecision(ctx); break;
                default:
                    ctx.Response.StatusCode = 404; ctx.Response.Close(); break;
            }
        }
        catch (Exception ex)
        {
            ModLogger.Log($"HTTP error: {ex.Message}");
            try { ctx.Response.StatusCode = 500; ctx.Response.Close(); } catch { }
        }
    }

    private void HandleGetState(HttpListenerContext ctx)
    {
        StateSnapshotCache.Refresh(CombatHooks.CurrentCombatManager);
        RespondJson(ctx, StateSnapshotCache.Json);
    }

    private void HandleGetStatus(HttpListenerContext ctx)
    {
        var cm = CombatHooks.CurrentCombatManager;
        StateSnapshotCache.Refresh(cm);
        RespondJson(ctx, JsonSerializer.Serialize(new StatusResponse
        {
            InBattle = StateSnapshotCache.InCombat,
            AwaitingDecision = DecisionGate.IsDecisionReady,
            ActionInFlight = DecisionGate.IsInFlight,
            StateRevision = StateSnapshotCache.Revision,
            InGame = cm != null,
        }));
    }

    private void HandlePostDecision(HttpListenerContext ctx)
    {
        using var reader = new StreamReader(ctx.Request.InputStream, Encoding.UTF8);
        var body = reader.ReadToEnd();
        var decision = JsonSerializer.Deserialize<AiDecision>(body);
        if (decision == null)
        {
            ctx.Response.StatusCode = 400;
            RespondJson(ctx, """{"status":"error","message":"invalid json"}""");
            return;
        }

        // POST 之前刷新一次主线程快照，确保门闩依据的是最新回合状态。
        StateSnapshotCache.Refresh(CombatHooks.CurrentCombatManager);
        if (!DecisionGate.TryBegin(decision))
        {
            ctx.Response.StatusCode = 409;
            RespondJson(ctx, """{"status":"busy","message":"game action is not ready"}""");
            return;
        }

        bool ok = MainThreadDispatcher.Execute(
            () => DecisionExecutor.Execute(CombatHooks.CurrentCombatManager, decision)
        );
        if (!ok) DecisionGate.Cancel();
        RespondJson(ctx, $"{{\"status\":\"{(ok ? "ok" : "error")}\"}}");
    }

    private static void RespondJson(HttpListenerContext ctx, string json)
    {
        var bytes = Encoding.UTF8.GetBytes(json);
        ctx.Response.ContentType = "application/json";
        ctx.Response.ContentLength64 = bytes.Length;
        ctx.Response.OutputStream.Write(bytes, 0, bytes.Length);
        ctx.Response.Close();
    }

    public void Dispose()
    {
        _running = false;
        _cts.Cancel();
        try { _listener.Stop(); } catch { }
        _listener.Close();
    }
}
