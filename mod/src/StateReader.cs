using System.Reflection;
using System.Runtime.CompilerServices;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Context;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.MonsterMoves.Intents;
using MegaCrit.Sts2.Core.Map;
using MegaCrit.Sts2.Core.Runs;

namespace Sts2AiMod;

/// <summary>通过纯反射从 STS2 游戏内存中读取游戏状态。</summary>
public static class StateReader
{
    /// <summary>读取完整游戏状态。</summary>
    public static GameStateJson? ReadFullState(CombatManager? combatManager)
    {
        try
        {
            var result = new GameStateJson();
            var runState = RunManager.Instance.DebugOnlyGetState();
            var player = runState == null ? null : LocalContext.GetMe(runState);

            if (runState != null)
            {
                result.Act = runState.CurrentActIndex + 1;
                result.Floor = runState.ActFloor;
                result.AscensionLevel = runState.AscensionLevel;
                result.RoomType = runState.CurrentRoom?.RoomType.ToString().ToUpperInvariant() ?? "";
                ReadMap(runState, result);
            }

            if (player != null)
            {
                ReadPlayer(player, result);
                result.Deck.AddRange(player.Deck.Cards.Select(c => ReadCard(c, player, PileType.Deck)));
                if (runState != null)
                    ReadTeammates(runState.Players, player, result);
            }

            if (combatManager == null)
            {
                UiStateReader.Apply(result);
                return result;
            }

            var stateField = combatManager.GetType()
                .GetField("_state", BindingFlags.NonPublic | BindingFlags.Instance);
            var state = stateField?.GetValue(combatManager);
            if (state == null)
            {
                UiStateReader.Apply(result);
                return result;
            }

            // 读取玩家
            var playersProp = state.GetType().GetProperty("Players");
            var players = playersProp?.GetValue(state) as System.Collections.IEnumerable;
            var combatPlayer = players?.Cast<Player>().FirstOrDefault() ?? player;
            if (combatPlayer != null && player == null)
            {
                ReadPlayer(combatPlayer, result);
            }

            // 读取怪物（敌人）
            var enemiesProp = state.GetType().GetProperty("Enemies");
            var enemies = enemiesProp?.GetValue(state) as System.Collections.IEnumerable;
            var combatState = combatPlayer?.Creature.CombatState;
            var playerTargets = combatState?.PlayerCreatures ?? Array.Empty<Creature>();
            var hittableEnemies = combatState?.HittableEnemies ?? Array.Empty<Creature>();
            if (enemies != null)
            {
                foreach (var creature in enemies)
                    result.Monsters.Add(ReadMonster((Creature)creature, playerTargets, hittableEnemies));
            }

            // 战斗状态
            var isInProgressProp = combatManager.GetType().GetProperty("IsInProgress");
            var isOverProp = combatManager.GetType().GetProperty("IsOverOrEnding");
            bool inProgress = isInProgressProp?.GetValue(combatManager) is true;
            bool isOver = isOverProp?.GetValue(combatManager) is true;
            result.InCombat = inProgress && !isOver;
            result.ActionInProgress = combatPlayer != null &&
                (combatManager.IsExecutingCardOrPotionEffect(combatPlayer) ||
                 combatManager.EndingPlayerTurnPhaseOne ||
                 combatManager.EndingPlayerTurnPhaseTwo);

            var roundProp = state.GetType().GetProperty("RoundNumber");
            result.Turn = (int)(roundProp?.GetValue(state) ?? 0);

            if (player != null)
            {
                if (combatState != null)
                    ReadTeamActions(combatManager, combatState, player, result);
            }

            if (result.InCombat)
                result.ScreenType = "COMBAT";
            UiStateReader.Apply(result);

            return result;
        }
        catch (Exception ex)
        {
            ModLogger.Log($"StateReader error: {ex.Message}");
            return null;
        }
    }

    private static void ReadMap(RunState runState, GameStateJson result)
    {
        var map = runState.Map;
        if (map == null) return;

        var points = new HashSet<MapPoint>(map.GetAllMapPoints());
        points.UnionWith(map.startMapPoints);
        points.Add(map.StartingMapPoint);
        points.Add(map.BossMapPoint);
        if (map.SecondBossMapPoint != null) points.Add(map.SecondBossMapPoint);

        result.Map.CurrentNodeId = runState.CurrentMapCoord is { } current
            ? MapNodeId(current.row, current.col)
            : "";
        var visited = runState.VisitedMapCoords
            .Select(coord => MapNodeId(coord.row, coord.col))
            .ToHashSet(StringComparer.Ordinal);

        var uniquePoints = points
            .GroupBy(point => MapNodeId(point.coord.row, point.coord.col))
            .Select(group => group.OrderByDescending(point => point.Children.Count).First());
        foreach (var point in uniquePoints.OrderBy(point => point.coord.row).ThenBy(point => point.coord.col))
        {
            var id = MapNodeId(point.coord.row, point.coord.col);
            result.Map.Nodes.Add(new MapNodeJson
            {
                Id = id,
                Row = point.coord.row,
                Column = point.coord.col,
                Type = point.PointType.ToString().ToUpperInvariant(),
                Children = point.Children
                    .Select(child => MapNodeId(child.coord.row, child.coord.col))
                    .OrderBy(child => child, StringComparer.Ordinal)
                    .ToList(),
                Visited = visited.Contains(id),
            });
        }
    }

    private static void ReadTeammates(IEnumerable<Player> players, Player localPlayer, GameStateJson result)
    {
        foreach (var teammate in players.Where(player => !ReferenceEquals(player, localPlayer)))
        {
            var pcs = teammate.PlayerCombatState;
            result.Teammates.Add(new TeammateStateJson
            {
                NetId = teammate.NetId.ToString(),
                Character = teammate.Character.Id.ToString(),
                CurrentHp = teammate.Creature.CurrentHp,
                MaxHp = teammate.Creature.MaxHp,
                Block = teammate.Creature.Block,
                Energy = pcs?.Energy ?? 0,
                HandCount = pcs?.Hand.Cards.Count ?? 0,
                Turn = pcs?.TurnNumber ?? 0,
                Phase = pcs?.Phase.ToString() ?? "None",
                IsAlive = teammate.Creature.IsAlive,
                Powers = ReadPowers(teammate.Creature),
            });
        }
    }

    private static void ReadTeamActions(
        CombatManager combatManager,
        ICombatState combatState,
        Player localPlayer,
        GameStateJson result)
    {
        foreach (var entry in combatManager.History.Entries
                     .Where(entry => entry.HappenedThisTurn(combatState) && entry.Actor.IsPlayer)
                     .TakeLast(30))
        {
            var actor = entry.Actor.Player;
            if (actor == null) continue;
            result.TeamActions.Add(new TeamActionJson
            {
                ActorNetId = actor.NetId.ToString(),
                Actor = actor.Character.Id.ToString(),
                Description = entry.Description,
                IsLocal = ReferenceEquals(actor, localPlayer),
            });
        }
    }

    private static string MapNodeId(int row, int column) => $"{row}:{column}";

    private static void ReadPlayer(Player player, GameStateJson result)
    {
        result.CharClass = player.Character.Id.ToString();
        result.Player.Gold = player.Gold;

        result.Player.CurrentHp = player.Creature.CurrentHp;
        result.Player.MaxHp = player.Creature.MaxHp;
        result.Player.Block = player.Creature.Block;
        result.Player.Powers = ReadPowers(player.Creature);

        // PlayerCombatState (for energy, hand, piles)
        var pcs = player.PlayerCombatState;
        if (pcs != null)
        {
            result.Player.Energy = pcs.Energy;
            result.Player.MaxEnergy = pcs.MaxEnergy;
            result.Player.EnergyThisTurn = result.Player.MaxEnergy;
            result.Turn = pcs.TurnNumber;
            result.Player.Phase = pcs.Phase.ToString();

            // 手牌
            result.Hand.AddRange(pcs.Hand.Cards.Select(c => ReadCard(c, player)));

            // 弃牌堆
            result.DiscardPile.AddRange(pcs.DiscardPile.Cards.Select(c => ReadCard(c, player)));

            // 抽牌堆
            result.DrawPileCount = pcs.DrawPile.Cards.Count;

            // 消耗堆
            result.ExhaustPile.AddRange(pcs.ExhaustPile.Cards.Select(c => ReadCard(c, player)));
        }

        // 遗物
        foreach (var relic in player.Relics)
        {
            result.Relics.Add(new RelicStateJson
            {
                Id = relic.Id.ToString(),
                Name = SafeText(() => relic.Title.GetFormattedText()),
                Counter = ReadIntPropertyOrField(relic, "Counter", -1),
            });
        }

        // 药水
        for (int slot = 0; slot < player.PotionSlots.Count; slot++)
        {
            var potion = player.PotionSlots[slot];
            if (potion == null) continue;

            var target = GetDefaultPotionTarget(potion, player);
            result.Potions.Add(new PotionStateJson
            {
                Slot = slot,
                Id = potion.Id.ToString(),
                Name = SafeText(() => potion.Title.GetFormattedText()),
                TargetType = potion.TargetType.ToString(),
                CanUse = player.CanUseOrRemovePotions && potion.IsValidTarget(target),
                Description = SafeText(() => potion.DynamicDescription.GetFormattedText()),
            });
        }
    }

    private static MonsterStateJson ReadMonster(
        Creature creature,
        IReadOnlyList<Creature> playerTargets,
        IReadOnlyList<Creature> hittableEnemies)
    {
        var nextMove = creature.Monster?.NextMove;
        var intents = nextMove?.Intents ?? [];
        var attackIntents = intents.OfType<AttackIntent>().ToList();
        var (intentDamage, intentHits) = ReadAttackDamage(attackIntents, playerTargets, creature);
        var targetIndex = -1;
        for (var i = 0; i < hittableEnemies.Count; i++)
        {
            if (ReferenceEquals(hittableEnemies[i], creature))
            {
                targetIndex = i;
                break;
            }
        }

        return new MonsterStateJson
        {
            Id = creature.ModelId.ToString(),
            Name = creature.Name,
            CurrentHp = creature.CurrentHp,
            MaxHp = creature.MaxHp,
            Block = creature.Block,
            Intent = NormalizeIntent(intents),
            IntentDamage = intentDamage,
            IntentHits = intentHits,
            IsGone = !creature.IsAlive,
            Targetable = targetIndex >= 0,
            TargetIndex = targetIndex,
            Powers = ReadPowers(creature),
        };
    }

    internal static CardStateJson ReadCard(CardModel card, Player player, PileType pileType = PileType.Hand)
    {
        var cost = card.EnergyCost.Canonical;
        var costForTurn = card.EnergyCost.GetAmountToSpend();
        var target = GetDefaultCardTarget(card, player);
        var canPlay = card.CanPlayTargeting(target);
        var vars = ReadDynamicVars(card.DynamicVars);

        return new CardStateJson
        {
            // 同名卡牌需要不同标识，否则连续出牌时状态哈希可能不变化。
            Uuid = $"{card.Id}:{RuntimeHelpers.GetHashCode(card)}",
            Id = card.Id.ToString(),
            Name = SafeText(() => card.Title),
            Cost = cost,
            CostForTurn = costForTurn,
            CardType = card.Type.ToString().ToUpperInvariant(),
            Rarity = card.Rarity.ToString().ToUpperInvariant(),
            TargetType = card.TargetType.ToString(),
            HasTarget = card.TargetType == TargetType.AnyEnemy || card.TargetType == TargetType.AnyAlly || card.TargetType == TargetType.AnyPlayer,
            IsPlayable = canPlay,
            PlayableReason = canPlay ? "OK" : GetUnplayableReason(card),
            Upgrades = card.CurrentUpgradeLevel,
            Damage = GetVar(vars, "CalculatedDamage", "Damage"),
            Block = GetVar(vars, "CalculatedBlock", "Block"),
            MagicNumber = GetMagicNumber(vars),
            Exhausts = card.Keywords.Any(k => k.ToString() == "Exhaust") || ReadBoolPropertyOrField(card, "ExhaustOnNextPlay"),
            Ethereal = card.Keywords.Any(k => k.ToString() == "Ethereal"),
            Description = SafeText(() => card.GetDescriptionForPile(pileType, target)),
        };
    }

    private static List<PowerStateJson> ReadPowers(Creature creature)
    {
        var result = new List<PowerStateJson>();
        foreach (var pow in creature.Powers)
        {
            result.Add(new PowerStateJson
            {
                Id = pow.Id.ToString(),
                Name = SafeText(() => pow.Title.GetFormattedText()),
                Amount = pow.DisplayAmount,
            });
        }
        return result;
    }

    private static Creature? GetDefaultCardTarget(CardModel card, Player player)
    {
        var state = player.Creature.CombatState;
        return card.TargetType switch
        {
            TargetType.AnyEnemy => state?.HittableEnemies.FirstOrDefault() ?? state?.Enemies.FirstOrDefault(e => e.IsAlive),
            TargetType.AnyAlly => state?.PlayerCreatures.FirstOrDefault(c => c.IsAlive && c != player.Creature),
            TargetType.AnyPlayer => player.Creature,
            _ => null,
        };
    }

    private static Creature? GetDefaultPotionTarget(PotionModel potion, Player player)
    {
        var state = player.Creature.CombatState;
        return potion.TargetType switch
        {
            TargetType.Self => player.Creature,
            TargetType.AnyEnemy => state?.HittableEnemies.FirstOrDefault() ?? state?.Enemies.FirstOrDefault(e => e.IsAlive),
            TargetType.AnyAlly => state?.PlayerCreatures.FirstOrDefault(c => c.IsAlive && c != player.Creature),
            TargetType.AnyPlayer => player.Creature,
            _ => null,
        };
    }

    private static string GetUnplayableReason(CardModel card)
    {
        try
        {
            var ok = card.CanPlay(out var reason, out var preventer);
            if (ok) return "INVALID_TARGET";
            return preventer == null ? reason.ToString() : $"{reason}:{preventer.Id}";
        }
        catch (Exception ex)
        {
            return ex.GetType().Name;
        }
    }

    private static Dictionary<string, int> ReadDynamicVars(System.Collections.Generic.IEnumerable<KeyValuePair<string, MegaCrit.Sts2.Core.Localization.DynamicVars.DynamicVar>> vars)
        => vars.ToDictionary(kv => kv.Key, kv => kv.Value.IntValue);

    private static int GetVar(Dictionary<string, int> vars, params string[] names)
    {
        foreach (var name in names)
            if (vars.TryGetValue(name, out var value))
                return value;
        return 0;
    }

    private static int GetMagicNumber(Dictionary<string, int> vars)
    {
        foreach (var pair in vars)
        {
            if (pair.Key is "Damage" or "CalculatedDamage" or "Block" or "CalculatedBlock")
                continue;
            return pair.Value;
        }
        return 0;
    }

    private static string NormalizeIntent(IEnumerable<AbstractIntent> intents)
    {
        var names = intents
            .Select(i => i.IntentType.ToString().ToUpperInvariant())
            .Distinct()
            .ToList();
        return names.Count == 0 ? "NONE" : string.Join("_", names);
    }

    private static (int Damage, int Hits) ReadAttackDamage(
        IReadOnlyList<AttackIntent> attacks,
        IReadOnlyList<Creature> targets,
        Creature owner)
    {
        if (attacks.Count == 0) return (0, 0);
        try
        {
            if (attacks.Count == 1)
            {
                var attack = attacks[0];
                return (attack.GetSingleDamage(targets, owner), Math.Max(1, attack.Repeats));
            }

            // 极少数复合攻击包含多个不同伤害段，旧协议无法逐段表达，改为总伤害一次。
            return (attacks.Sum(a => a.GetTotalDamage(targets, owner)), 1);
        }
        catch (Exception ex)
        {
            ModLogger.Log($"Intent damage calculation failed for {owner.ModelId}: {ex.Message}");
            return (0, 0);
        }
    }

    private static int ReadIntPropertyOrField(object obj, string name, int fallback)
    {
        var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
        var prop = obj.GetType().GetProperty(name, flags);
        if (prop?.GetValue(obj) is IConvertible propValue)
            return Convert.ToInt32(propValue);
        var field = obj.GetType().GetField(name, flags);
        if (field?.GetValue(obj) is IConvertible fieldValue)
            return Convert.ToInt32(fieldValue);
        return fallback;
    }

    private static bool ReadBoolPropertyOrField(object obj, string name)
    {
        var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
        var prop = obj.GetType().GetProperty(name, flags);
        if (prop?.GetValue(obj) is bool propValue)
            return propValue;
        var field = obj.GetType().GetField(name, flags);
        return field?.GetValue(obj) is bool fieldValue && fieldValue;
    }

    internal static string SafeText(Func<string> read)
    {
        try { return read(); }
        catch { return ""; }
    }
}
