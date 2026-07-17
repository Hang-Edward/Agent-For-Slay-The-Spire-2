using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using MegaCrit.Sts2.Core.Combat;

namespace Sts2AiMod;

/// <summary>在 Godot 主线程生成不可变 JSON 快照，HTTP 线程只读取缓存。</summary>
public static class StateSnapshotCache
{
    private static readonly object Sync = new();
    private static string _json = JsonSerializer.Serialize(new GameStateJson());
    private static string _fingerprint = "";
    private static long _revision;
    private static bool _inCombat;

    public static string Json => Volatile.Read(ref _json);
    public static long Revision => Interlocked.Read(ref _revision);
    public static bool InCombat => Volatile.Read(ref _inCombat);

    public static bool Refresh(CombatManager? combatManager)
    {
        return MainThreadDispatcher.Execute(() =>
        {
            var state = StateReader.ReadFullState(combatManager) ?? new GameStateJson();

            // 此时状态尚未写入门闩元数据，因此哈希只代表真实游戏状态。
            var coreJson = JsonSerializer.Serialize(state);
            var fingerprint = Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(coreJson))
            );

            long revision;
            lock (Sync)
            {
                if (!string.Equals(_fingerprint, fingerprint, StringComparison.Ordinal))
                {
                    _fingerprint = fingerprint;
                    _revision++;
                }
                revision = _revision;
            }

            DecisionGate.Observe(state, fingerprint);
            state.StateRevision = revision;

            Volatile.Write(ref _inCombat, state.InCombat);
            Volatile.Write(ref _json, JsonSerializer.Serialize(state));
            return true;
        });
    }
}

/// <summary>确保同一时间最多有一个游戏动作，并等待动作队列真正稳定。</summary>
public static class DecisionGate
{
    private static readonly object Sync = new();
    private static bool _inFlight;
    private static bool _decisionReady;
    private static string _actionType = "";
    private static string _baselineFingerprint = "";
    private static string _lastFingerprint = "";
    private static int _baselineTurn;
    private static int _lastTurn;
    private static DateTime _notBeforeUtc;
    private static DateTime _deadlineUtc;

    public static bool IsInFlight
    {
        get { lock (Sync) return _inFlight; }
    }

    public static bool IsDecisionReady
    {
        get { lock (Sync) return _decisionReady; }
    }

    public static bool TryBegin(AiDecision decision)
    {
        lock (Sync)
        {
            if (_inFlight || !_decisionReady) return false;

            _inFlight = true;
            _decisionReady = false;
            _actionType = decision.Type;
            _baselineFingerprint = _lastFingerprint;
            _baselineTurn = _lastTurn;
            _notBeforeUtc = DateTime.UtcNow.AddMilliseconds(150);
            _deadlineUtc = DateTime.UtcNow.AddSeconds(10);
            return true;
        }
    }

    public static void Cancel()
    {
        lock (Sync)
        {
            _inFlight = false;
            _decisionReady = true;
            _actionType = "";
        }
    }

    public static void Observe(GameStateJson state, string fingerprint)
    {
        lock (Sync)
        {
            _lastFingerprint = fingerprint;
            _lastTurn = state.Turn;

            if (_inFlight && IsSettled(state, fingerprint))
            {
                _inFlight = false;
                _actionType = "";
            }

            var isPlayPhase = string.Equals(state.Player.Phase, "Play", StringComparison.Ordinal);
            var combatReady = state.InCombat && state.ScreenType == "COMBAT" && isPlayPhase;
            var choiceReady = state.ScreenType != "COMBAT" && state.Options.Any(o => o.Enabled);
            _decisionReady = DecisionGatePolicy.CanAcceptDecision(
                combatReady, choiceReady, state.ActionInProgress, _inFlight);
            state.ActionInFlight = _inFlight;
            state.DecisionReady = _decisionReady;
        }
    }

    private static bool IsSettled(GameStateJson state, string fingerprint)
    {
        if (DateTime.UtcNow >= _deadlineUtc)
        {
            ModLogger.Log($"Action {_actionType} timed out waiting for state change; releasing gate");
            return true;
        }
        var notBeforeElapsed = DateTime.UtcNow >= _notBeforeUtc;
        if (!notBeforeElapsed) return false;

        var choiceReady = state.ScreenType != "COMBAT" && state.Options.Any(o => o.Enabled);
        if (DecisionGatePolicy.ShouldSettleOnChoice(choiceReady, notBeforeElapsed)) return true;
        if (state.ActionInProgress) return false;

        if (string.Equals(_actionType, "end_turn", StringComparison.Ordinal))
            return state.Turn > _baselineTurn;

        return !string.Equals(fingerprint, _baselineFingerprint, StringComparison.Ordinal);
    }
}
