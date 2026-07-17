namespace Sts2AiMod;

/// <summary>集中定义动作门的放行规则，避免战斗内选择弹窗与卡牌动作互相等待。</summary>
public static class DecisionGatePolicy
{
    public static bool CanAcceptDecision(
        bool combatReady,
        bool choiceReady,
        bool actionInProgress,
        bool inFlight)
    {
        if (inFlight) return false;
        return choiceReady || (combatReady && !actionInProgress);
    }

    public static bool ShouldSettleOnChoice(bool choiceReady, bool notBeforeElapsed)
    {
        return choiceReady && notBeforeElapsed;
    }
}
