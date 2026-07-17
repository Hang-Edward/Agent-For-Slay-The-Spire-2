using System.Reflection;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Models;

namespace Sts2AiMod;

/// <summary>通过反射执行 AI 决策（出牌、结束回合等）。</summary>
public static class DecisionExecutor
{
    private static readonly Type? CardModelType;

    static DecisionExecutor()
    {
        // 通过反射加载 STS2 类型以避免编译时引用内部类型问题
        var sts2Asm = typeof(CombatManager).Assembly;
        CardModelType = sts2Asm.GetType("MegaCrit.Sts2.Core.Models.CardModel");
    }

    public static bool Execute(CombatManager? combatManager, AiDecision decision)
    {
        try
        {
            if (decision.Type == "choose_option")
            {
                var ok = UiActionRegistry.Execute(decision.OptionIndex);
                if (ok) ModLogger.Log($"Selected UI option [{decision.OptionIndex}]");
                return ok;
            }

            // 战斗动作仍要求有效的 CombatManager。
            if (combatManager == null) return false;
            return decision.Type switch
            {
                "play_card" => PlayCard(combatManager, decision),
                "use_potion" => UsePotion(combatManager, decision),
                "end_turn" => EndTurn(combatManager),
                _ => false,
            };
        }
        catch (Exception ex)
        {
            ModLogger.Log($"Decision execution failed: {ex.Message}");
            return false;
        }
    }

    private static bool PlayCard(CombatManager combatManager, AiDecision decision)
    {
        var player = GetPlayer(combatManager);
        if (player == null) return false;

        var hand = player.PlayerCombatState?.Hand;
        if (hand == null) return false;

        var cardList = hand.Cards.ToList();
        if (decision.HandIndex < 0 || decision.HandIndex >= cardList.Count)
            return false;

        var card = cardList[decision.HandIndex];

        var target = GetCardTarget(player, card, decision.MonsterIndex);
        if (!card.CanPlayTargeting(target))
        {
            ModLogger.Log($"Card [{decision.HandIndex}] {card.Title} is not playable for target {decision.MonsterIndex}");
            return false;
        }

        var ok = card.TryManualPlay(target);
        if (!ok) return false;

        ModLogger.Log($"Played card [{decision.HandIndex}] {card.Title}");
        return true;
    }

    private static bool UsePotion(CombatManager combatManager, AiDecision decision)
    {
        var player = GetPlayer(combatManager);
        if (player == null) return false;
        if (decision.PotionSlot < 0 || decision.PotionSlot >= player.PotionSlots.Count)
            return false;

        var potion = player.PotionSlots[decision.PotionSlot];
        if (potion == null) return false;

        var target = GetPotionTarget(player, potion, decision.MonsterIndex);
        if (!player.CanUseOrRemovePotions || !potion.IsValidTarget(target))
        {
            ModLogger.Log($"Potion [{decision.PotionSlot}] {potion.Title.GetFormattedText()} is not usable for target {decision.MonsterIndex}");
            return false;
        }

        potion.EnqueueManualUse(target);
        ModLogger.Log($"Used potion [{decision.PotionSlot}] {potion.Title.GetFormattedText()}");
        return true;
    }

    private static bool EndTurn(CombatManager combatManager)
    {
        var player = GetPlayer(combatManager);
        if (player == null) return false;

        // 只调用 OnEndedTurnLocally 会更新本地 UI 状态，但不会让战斗队列真正进入敌方回合。
        PlayerCmd.EndTurn(player, canBackOut: false);
        ModLogger.Log("Ended turn");
        return true;
    }

    private static Player? GetPlayer(CombatManager cm)
    {
        var state = GetCombatState(cm);
        if (state == null) return null;
        var playersProp = state.GetType().GetProperty("Players");
        var players = playersProp?.GetValue(state) as System.Collections.IEnumerable;
        return players?.Cast<Player>().FirstOrDefault();
    }

    private static Creature? GetCardTarget(Player player, CardModel card, int monsterIndex)
    {
        var state = player.Creature.CombatState;
        return card.TargetType switch
        {
            TargetType.AnyEnemy => GetEnemyByIndex(state, monsterIndex),
            TargetType.AnyAlly => state?.PlayerCreatures.FirstOrDefault(c => c.IsAlive && c != player.Creature),
            TargetType.AnyPlayer => player.Creature,
            _ => null,
        };
    }

    private static Creature? GetPotionTarget(Player player, PotionModel potion, int monsterIndex)
    {
        var state = player.Creature.CombatState;
        return potion.TargetType switch
        {
            TargetType.Self => player.Creature,
            TargetType.AnyEnemy => GetEnemyByIndex(state, monsterIndex),
            TargetType.AnyAlly => state?.PlayerCreatures.FirstOrDefault(c => c.IsAlive && c != player.Creature),
            TargetType.AnyPlayer => player.Creature,
            _ => null,
        };
    }

    private static Creature? GetEnemyByIndex(ICombatState? state, int monsterIndex)
    {
        if (state == null) return null;
        var enemies = state.HittableEnemies.Count > 0
            ? state.HittableEnemies
            : state.Enemies.Where(e => e.IsAlive).ToList();
        var index = monsterIndex >= 0 ? monsterIndex : 0;
        return index < enemies.Count ? enemies[index] : null;
    }

    private static object? GetCombatState(CombatManager cm)
    {
        var field = typeof(CombatManager).GetField("_state",
            BindingFlags.NonPublic | BindingFlags.Instance);
        return field?.GetValue(cm);
    }
}
