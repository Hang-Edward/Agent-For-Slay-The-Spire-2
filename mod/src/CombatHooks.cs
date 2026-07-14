using System.Reflection;
using HarmonyLib;
using MegaCrit.Sts2.Core.Combat;

namespace Sts2AiMod;

/// <summary>Harmony 补丁 — 挂钩战斗系统事件。</summary>
[HarmonyPatch]
public static class CombatHooks
{
    internal static CombatManager? CurrentCombatManager { get; private set; }

    private static readonly FieldInfo CombatManagerStateField =
        typeof(CombatManager).GetField("_state", BindingFlags.NonPublic | BindingFlags.Instance)!;

    /// <summary>通过反射获取 CombatManager 的 _state。</summary>
    public static object? GetState(this CombatManager cm)
        => CombatManagerStateField.GetValue(cm);

    [HarmonyPostfix]
    [HarmonyPatch(typeof(CombatManager), "StartTurn")]
    public static void OnStartTurn(CombatManager __instance)
    {
        CurrentCombatManager = __instance;
        ModLogger.Log("Combat turn started");
        TurnMonitor.OnTurnStarted(__instance);
    }

    [HarmonyPostfix]
    [HarmonyPatch(typeof(CombatManager), "OnEndedTurnLocally")]
    public static void OnPlayerEndedTurn(CombatManager __instance)
    {
        ModLogger.Log("Player ended turn");
        TurnMonitor.OnTurnEnded(__instance);
    }

    [HarmonyPostfix]
    [HarmonyPatch(typeof(CombatManager), "EndCombatInternal")]
    public static void OnCombatEnd(CombatManager __instance)
    {
        CurrentCombatManager = null;
        ModLogger.Log("Combat ended");
    }
}

public static class TurnMonitor
{
    public static bool IsWaitingForDecision { get; set; }

    internal static void OnTurnStarted(CombatManager cm) => IsWaitingForDecision = true;
    internal static void OnTurnEnded(CombatManager cm) => IsWaitingForDecision = false;
    internal static void OnDecisionReceived() => IsWaitingForDecision = false;
}
