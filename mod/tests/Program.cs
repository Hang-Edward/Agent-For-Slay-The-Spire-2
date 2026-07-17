using Sts2AiMod;

static void Assert(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

// 普通战斗动作执行期间不能重入。
Assert(!DecisionGatePolicy.CanAcceptDecision(
    combatReady: true,
    choiceReady: false,
    actionInProgress: true,
    inFlight: false), "combat action should remain blocked while an action is executing");

// 战斗内选牌弹窗会保持 actionInProgress，存在可用选项时仍必须放行。
Assert(DecisionGatePolicy.CanAcceptDecision(
    combatReady: false,
    choiceReady: true,
    actionInProgress: true,
    inFlight: false), "visible choice overlay should be actionable during a card effect");

Assert(DecisionGatePolicy.ShouldSettleOnChoice(
    choiceReady: true,
    notBeforeElapsed: true), "opening a choice overlay should settle the preceding action");

Console.WriteLine("DecisionGatePolicy tests passed.");
