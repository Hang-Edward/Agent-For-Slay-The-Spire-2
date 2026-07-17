using System.Reflection;
using Godot;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Context;
using MegaCrit.Sts2.Core.Entities.Merchant;
using MegaCrit.Sts2.Core.Helpers;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Nodes.Cards.Holders;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Events;
using MegaCrit.Sts2.Core.Nodes.Events.Custom.CrystalSphere;
using MegaCrit.Sts2.Core.Nodes.GodotExtensions;
using MegaCrit.Sts2.Core.Nodes.RestSite;
using MegaCrit.Sts2.Core.Nodes.Rewards;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens;
using MegaCrit.Sts2.Core.Nodes.Screens.CardSelection;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;
using MegaCrit.Sts2.Core.Nodes.Screens.Shops;
using MegaCrit.Sts2.Core.Nodes.Screens.TreasureRoomRelic;
using MegaCrit.Sts2.Core.Nodes.Screens.GameOverScreen;
using MegaCrit.Sts2.Core.Nodes.Screens.MainMenu;
using MegaCrit.Sts2.Core.Nodes.Relics;
using MegaCrit.Sts2.Core.Rewards;
using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.Runs;

namespace Sts2AiMod;

/// <summary>
/// 从当前 Godot 节点树读取所有非战斗选择，并把选择映射为稳定的 option_index。
/// 事件本身不做名称硬编码，因此新事件和多阶段事件也能通过同一协议处理。
/// </summary>
public static class UiStateReader
{
    private static bool _loggedTreasureDiagnostics;

    public static void Apply(GameStateJson state)
    {
        UiActionRegistry.BeginSnapshot();

        try
        {
            var modal = NModalContainer.Instance?.OpenModal as Node;
            if (modal != null && BuildGenericChoices(state, modal, "MODAL"))
                return;
        }
        catch (Exception ex) { ModLogger.Log($"Ui probe modal failed: {ex.Message}"); }

        // 无人值守启动时由 Agent 自行进入已有存档，不依赖鼠标或屏幕识别。
        try
        {
            if (!IsRunInProgressSafe() && BuildMainMenu(state))
                return;
        }
        catch (Exception ex) { ModLogger.Log($"Ui probe main menu failed: {ex.Message}"); }

        // 终端奖励完成后，NRewardsScreen 可能仍短暂留在栈顶，但地图已经可操作。
        try
        {
            if (NMapScreen.Instance is { IsOpen: true } openMap && BuildMap(state, openMap))
                return;
        }
        catch (Exception ex) { ModLogger.Log($"Ui probe map failed: {ex.Message}"); }

        try
        {
            var overlay = NOverlayStack.Instance?.Peek() as Node;
            if (overlay != null && BuildOverlay(state, overlay))
                return;
        }
        catch (Exception ex) { ModLogger.Log($"Ui probe overlay failed: {ex.Message}"); }

        if (state.InCombat)
        {
            state.ScreenType = "COMBAT";
            return;
        }

        // 战斗结束后房间类型仍可能是 Monster/Elite/Boss，必须显式暴露继续按钮。
        try
        {
            if (BuildVictory(state))
                return;
        }
        catch (Exception ex) { ModLogger.Log($"Ui probe victory failed: {ex.Message}"); }

        var room = GetRunStateSafe()?.CurrentRoom;
        switch (room?.RoomType)
        {
            case RoomType.Event:
                TryBuildRoom(state, BuildEvent, "event");
                break;
            case RoomType.RestSite:
                TryBuildRoom(state, BuildRestSite, "rest");
                break;
            case RoomType.Shop:
                TryBuildRoom(state, BuildShop, "shop");
                break;
            case RoomType.Treasure:
                TryBuildRoom(state, BuildTreasure, "treasure");
                break;
            default:
                state.ScreenType = IsRunInProgressSafe() ? "WAITING" : "MAIN_MENU";
                break;
        }
    }

    private static bool IsRunInProgressSafe()
    {
        try { return RunManager.Instance.IsInProgress; }
        catch (Exception ex)
        {
            ModLogger.Log($"Run progress probe failed: {ex.Message}");
            return false;
        }
    }

    private static RunState? GetRunStateSafe()
    {
        try { return RunManager.Instance.DebugOnlyGetState(); }
        catch (Exception ex)
        {
            ModLogger.Log($"Run state probe failed: {ex.Message}");
            return null;
        }
    }

    private static void TryBuildRoom(GameStateJson state, Func<GameStateJson, bool> build, string label)
    {
        try { build(state); }
        catch (Exception ex)
        {
            ModLogger.Log($"Ui build {label} failed: {ex.Message}");
            state.ScreenType = label.ToUpperInvariant();
        }
    }

    private static bool BuildMainMenu(GameStateJson state)
    {
        var root = ((SceneTree)Engine.GetMainLoop()).Root;
        var mainMenu = UiHelper.FindAll<NMainMenu>(root).FirstOrDefault();
        if (mainMenu == null)
            return false;

        state.ScreenType = "MAIN_MENU";
        var consumed = new HashSet<Node>();
        var continueButton = mainMenu.GetNodeOrNull<NMainMenuTextButton>("MainMenuTextButtons/ContinueButton");
        if (continueButton is { Visible: true, IsEnabled: true })
        {
            consumed.Add(continueButton);
            Add(state, NewOption("continue_run", "continue", "Continue run", "Load the existing saved run"),
                () => Click(continueButton));
        }
        AddMainMenuAutomationChoices(state, mainMenu, consumed);
        return true;
    }

    private static void AddMainMenuAutomationChoices(GameStateJson state, Node root, HashSet<Node> consumed)
    {
        foreach (var button in UiHelper.FindAll<NClickableControl>(root))
        {
            if (consumed.Contains(button) || !button.Visible || !button.IsEnabled) continue;
            var nodeName = button.Name.ToString();
            var label = ReadNodeLabel(button);
            var text = $"{nodeName} {button.GetType().Name} {label}";
            if (IsUnsafeAutomationChoice(text) || !IsMainMenuAutomationChoice(text)) continue;
            consumed.Add(button);
            Add(state, NewOption(MainMenuChoiceKind(text), nodeName,
                string.IsNullOrWhiteSpace(label) ? nodeName : label, button.GetType().Name), () => Click(button));
        }
    }

    private static bool IsMainMenuAutomationChoice(string text)
    {
        if (text.Contains("settings", StringComparison.OrdinalIgnoreCase)
            || text.Contains("options", StringComparison.OrdinalIgnoreCase)
            || text.Contains("compendium", StringComparison.OrdinalIgnoreCase)
            || text.Contains("credits", StringComparison.OrdinalIgnoreCase)
            || text.Contains("quit", StringComparison.OrdinalIgnoreCase)
            || text.Contains("exit", StringComparison.OrdinalIgnoreCase)
            || text.Contains("multiplayer", StringComparison.OrdinalIgnoreCase)
            || text.Contains("多人", StringComparison.OrdinalIgnoreCase)
            || text.Contains("reset", StringComparison.OrdinalIgnoreCase)
            || text.Contains("重置", StringComparison.OrdinalIgnoreCase)
            || text.Contains("display", StringComparison.OrdinalIgnoreCase)
            || text.Contains("monitor", StringComparison.OrdinalIgnoreCase)
            || text.Contains("dropdown", StringComparison.OrdinalIgnoreCase)
            || text.Contains("invite", StringComparison.OrdinalIgnoreCase)
            || text.Contains("邀请", StringComparison.OrdinalIgnoreCase))
            return false;
        return new[]
        {
            "singleplayer", "single player", "单人", "standard", "标准", "new run",
            "start", "begin", "embark", "ready", "confirm",
            "ironclad", "silent", "defect", "character", "continue", "resume"
        }.Any(token => text.Contains(token, StringComparison.OrdinalIgnoreCase));
    }

    private static string MainMenuChoiceKind(string text)
    {
        if (text.Contains("continue", StringComparison.OrdinalIgnoreCase)
            || text.Contains("resume", StringComparison.OrdinalIgnoreCase))
            return "continue_run";
        if (text.Contains("singleplayer", StringComparison.OrdinalIgnoreCase)
            || text.Contains("single player", StringComparison.OrdinalIgnoreCase)
            || text.Contains("单人", StringComparison.OrdinalIgnoreCase)
            || text.Contains("standard", StringComparison.OrdinalIgnoreCase)
            || text.Contains("标准", StringComparison.OrdinalIgnoreCase)
            || text.Contains("new run", StringComparison.OrdinalIgnoreCase)
            || text.Contains("play", StringComparison.OrdinalIgnoreCase))
            return "singleplayer";
        if (text.Contains("ironclad", StringComparison.OrdinalIgnoreCase)
            || text.Contains("silent", StringComparison.OrdinalIgnoreCase)
            || text.Contains("defect", StringComparison.OrdinalIgnoreCase)
            || text.Contains("character", StringComparison.OrdinalIgnoreCase))
            return "character";
        if (text.Contains("start", StringComparison.OrdinalIgnoreCase)
            || text.Contains("begin", StringComparison.OrdinalIgnoreCase)
            || text.Contains("embark", StringComparison.OrdinalIgnoreCase)
            || text.Contains("ready", StringComparison.OrdinalIgnoreCase))
            return "start_run";
        return "confirm";
    }

    private static bool BuildOverlay(GameStateJson state, Node overlay)
    {
        if (overlay is NRewardsScreen rewards)
        {
            state.ScreenType = "REWARDS";
            foreach (var button in UiHelper.FindAll<NRewardButton>(rewards))
            {
                var reward = button.Reward;
                if (reward == null) continue;
                var option = NewOption(RewardKind(reward), reward.GetType().Name,
                    StateReader.SafeText(() => reward.Description.GetFormattedText()), "");
                option.Enabled = button.IsEnabled;
                PopulateReward(option, reward);
                Add(state, option, () => Click(button));
            }
            var rewardPlayer = GetPlayer();
            var hasPotionReward = UiHelper.FindAll<NRewardButton>(rewards)
                .Any(button => button.Reward is PotionReward);
            if (hasPotionReward && rewardPlayer is { HasOpenPotionSlots: false })
            {
                foreach (var potion in rewardPlayer.Potions)
                {
                    var option = NewOption("discard_potion", potion.Id.ToString(),
                        $"Discard {StateReader.SafeText(() => potion.Title.GetFormattedText())}",
                        ReadFormattedProperty(potion, "DynamicDescription", "Description"));
                    option.Potion = ReadPotion(potion, rewardPlayer);
                    Add(state, option, () =>
                    {
                        TaskHelper.RunSafely(PotionCmd.Discard(potion));
                        return true;
                    });
                }
            }
            AddProceedButtons(state, rewards);
            return true;
        }

        if (overlay is NCardRewardSelectionScreen)
            return BuildCardChoices(state, overlay, "CARD_REWARD");
        if (overlay is NDeckUpgradeSelectScreen)
            return BuildCardChoices(state, overlay, "CARD_SELECT_UPGRADE");
        if (overlay is NDeckTransformSelectScreen)
            return BuildCardChoices(state, overlay, "CARD_SELECT_TRANSFORM");
        if (overlay is NDeckEnchantSelectScreen)
            return BuildCardChoices(state, overlay, "CARD_SELECT_ENCHANT");
        if (overlay is NDeckCardSelectScreen)
            return BuildCardChoices(state, overlay, "CARD_SELECT_DECK");
        if (overlay is NSimpleCardSelectScreen)
            return BuildCardChoices(state, overlay, "CARD_SELECT");
        if (overlay is NChooseACardSelectionScreen)
            return BuildCardChoices(state, overlay, "CARD_SELECT_COMBAT");
        if (overlay is NChooseABundleSelectionScreen)
            return BuildGenericChoices(state, overlay, "BUNDLE_SELECT");
        if (overlay is NChooseARelicSelection)
            return BuildRelicChoices(state, overlay);
        if (overlay is NCrystalSphereScreen crystalSphere)
            return BuildCrystalSphere(state, crystalSphere);
        if (overlay is NGameOverScreen gameOver)
            return BuildGameOver(state, gameOver);

        // Crystal Sphere 等特殊事件由其当前可点击节点驱动，多阶段状态会自然产生新 revision。
        return BuildGenericChoices(state, overlay, "SPECIAL_EVENT");
    }

    private static bool BuildCardChoices(GameStateJson state, Node screen, string screenType)
    {
        state.ScreenType = screenType;
        var player = GetPlayer();
        var selectedCards = ReadObjectSet(screen, "_selectedCards");
        foreach (var holder in UiHelper.FindAll<NCardHolder>(screen))
        {
            var card = holder.CardModel;
            if (card == null) continue;
            var option = NewOption("card", card.Id.ToString(), StateReader.SafeText(() => card.Title),
                StateReader.SafeText(() => card.GetDescriptionForPile(MegaCrit.Sts2.Core.Entities.Cards.PileType.Deck, null)));
            if (player != null) option.Card = StateReader.ReadCard(card, player, MegaCrit.Sts2.Core.Entities.Cards.PileType.Deck);
            option.Selected = selectedCards.Contains(card);
            Add(state, option, () =>
            {
                holder.EmitSignal(NCardHolder.SignalName.Pressed, holder);
                return true;
            });
        }

        AddNamedClickableChoices(state, screen, new[] { "Confirm", "Skip", "Cancel", "Proceed", "Alternative" });
        return true;
    }

    private static bool BuildRelicChoices(GameStateJson state, Node screen)
    {
        state.ScreenType = "RELIC_SELECT";
        foreach (var holder in UiHelper.FindAll<NRelicBasicHolder>(screen))
        {
            var relic = holder.Relic?.Model;
            if (relic == null) continue;
            var option = NewOption("relic", relic.Id.ToString(),
                StateReader.SafeText(() => relic.Title.GetFormattedText()),
                ReadFormattedProperty(relic, "DynamicDescription", "Description"));
            option.Relic = ReadRelic(relic);
            Add(state, option, () => Click(holder));
        }
        AddNamedClickableChoices(state, screen, new[] { "Skip", "Proceed", "Confirm" });
        return true;
    }

    private static bool BuildMap(GameStateJson state, NMapScreen map)
    {
        state.ScreenType = "MAP";
        foreach (var point in UiHelper.FindAll<NMapPoint>(map).Where(p => p.IsEnabled))
        {
            var coord = point.Point.coord;
            var kind = point.Point.PointType.ToString().ToUpperInvariant();
            var option = NewOption("map", $"{coord.row}:{coord.col}", kind, $"Travel to {kind}");
            option.Row = coord.row;
            option.Column = coord.col;
            Add(state, option, () => Click(point));
        }
        return true;
    }

    private static bool BuildEvent(GameStateJson state)
    {
        state.ScreenType = "EVENT";
        var root = GetRoomNode("EventRoom") ?? NEventRoom.Instance;
        if (root == null) return false;

        var buttons = UiHelper.FindAll<NEventOptionButton>(root)
            .Where(button => button.IsEnabled && !button.Option.IsLocked)
            .ToList();
        var safeButtons = buttons.Where(button =>
            button.Option.WillKillPlayer == null
            || button.Event.Owner == null
            || !button.Option.WillKillPlayer(button.Event.Owner)).ToHashSet();
        var hasSafeChoice = safeButtons.Count > 0;

        foreach (var button in buttons)
        {
            var option = NewOption(button.Option.IsProceed ? "proceed" : "event",
                button.Event.Id.ToString(),
                StateReader.SafeText(() => button.Option.Title.GetFormattedText()),
                StateReader.SafeText(() => button.Option.Description.GetFormattedText()));
            // 若存在安全选项，不允许模型误选会立即死亡的事件分支；全都致死时仍保留选择。
            option.Enabled = !hasSafeChoice || safeButtons.Contains(button);
            Add(state, option, () => Click(button));
        }

        if (state.Options.Count == 0)
            AddNamedClickableChoices(state, root, new[] { "DialogueHitbox", "Proceed", "Continue", "Cell" });
        AddFallbackClickableChoices(state, root);
        return true;
    }

    private static bool BuildVictory(GameStateJson state)
    {
        var room = NCombatRoom.Instance;
        var proceed = room?.ProceedButton;
        if (room == null || proceed == null || !proceed.Visible || !proceed.IsEnabled)
            return false;

        state.ScreenType = "VICTORY";
        Add(state, NewOption("proceed", proceed.Name.ToString(), "Proceed", "Leave the completed combat room"),
            () => Click(proceed));
        return true;
    }

    private static bool BuildCrystalSphere(GameStateJson state, NCrystalSphereScreen screen)
    {
        state.ScreenType = "CRYSTAL_SPHERE";
        var proceed = screen.GetNodeOrNull<NProceedButton>("%ProceedButton");
        if (proceed is { Visible: true, IsEnabled: true })
        {
            Add(state, NewOption("proceed", proceed.Name.ToString(), "Proceed", "Leave the Crystal Sphere"),
                () => Click(proceed));
            return true;
        }

        var cells = screen.GetNodeOrNull<Control>("%Cells");
        if (cells != null)
        {
            foreach (var cell in UiHelper.FindAll<NCrystalSphereCell>(cells)
                         .Where(cell => cell.Visible && cell.IsEnabled && cell.Entity.IsHidden))
            {
                var option = NewOption("crystal_cell", $"{cell.Entity.X}:{cell.Entity.Y}",
                    $"Hidden cell ({cell.Entity.X}, {cell.Entity.Y})", "Perform a divination on this hidden cell");
                option.Row = cell.Entity.Y;
                option.Column = cell.Entity.X;
                Add(state, option, () => Click(cell));
            }
        }
        return true;
    }

    private static bool BuildGameOver(GameStateJson state, NGameOverScreen screen)
    {
        state.ScreenType = "GAME_OVER";
        foreach (var button in UiHelper.FindAll<NGameOverContinueButton>(screen)
                     .Where(button => button.Visible && button.IsEnabled))
            Add(state, NewOption("continue", button.Name.ToString(), "Continue", "Advance the run summary"),
                () => Click(button));
        foreach (var button in UiHelper.FindAll<NReturnToMainMenuButton>(screen)
                     .Where(button => button.Visible && button.IsEnabled))
            Add(state, NewOption("main_menu", button.Name.ToString(), "Return to main menu", "Finish this run"),
                () => Click(button));
        return true;
    }

    private static bool BuildRestSite(GameStateJson state)
    {
        state.ScreenType = "REST";
        var room = NRestSiteRoom.Instance ?? GetRoomNode("RestSiteRoom");
        if (room == null) return false;

        foreach (var button in UiHelper.FindAll<NRestSiteButton>(room))
        {
            var rest = button.Option;
            var option = NewOption("rest", rest.OptionId,
                StateReader.SafeText(() => rest.Title.GetFormattedText()),
                StateReader.SafeText(() => rest.Description.GetFormattedText()));
            option.Enabled = rest.IsEnabled && button.IsEnabled;
            Add(state, option, () => Click(button));
        }
        AddProceedButtons(state, room);
        return true;
    }

    private static bool BuildShop(GameStateJson state)
    {
        state.ScreenType = "SHOP";
        var room = NMerchantRoom.Instance;
        if (room == null) return false;

        if (!room.Inventory.IsOpen)
        {
            // 已无任何买得起的库存时不再开放商店入口，避免 Open/Back 无限循环。
            var hasAffordableStock = room.Inventory.GetAllSlots().Any(slot =>
                slot.Entry is { IsStocked: true, EnoughGold: true });
            if (hasAffordableStock)
            {
                Add(state, NewOption("open_shop", "merchant", "Open merchant", "View items for sale"), () =>
                {
                    room.OpenInventory();
                    return true;
                });
            }
            AddProceedButtons(state, room);
            return true;
        }

        foreach (var slot in room.Inventory.GetAllSlots())
        {
            var entry = slot.Entry;
            if (entry == null || !entry.IsStocked) continue;
            var option = NewOption("buy", entry.GetType().Name, MerchantName(entry), MerchantDescription(entry));
            option.Cost = ReadInt(entry, "Cost", -1);
            option.Enabled = entry.EnoughGold;
            PopulateMerchantOption(option, entry);
            Add(state, option, () =>
            {
                TaskHelper.RunSafely(entry.OnTryPurchaseWrapper(room.Inventory.Inventory));
                return true;
            });
        }
        AddNamedClickableChoices(state, room.Inventory, new[] { "Back" });
        return true;
    }

    private static bool BuildTreasure(GameStateJson state)
    {
        state.ScreenType = "TREASURE";
        var root = ((SceneTree)Engine.GetMainLoop()).Root;
        var room = GetRoomNode("TreasureRoom") as NTreasureRoom
                   ?? UiHelper.FindAll<NTreasureRoom>(root).FirstOrDefault();
        if (room == null)
        {
            return false;
        }

        try
        {
            foreach (var holder in UiHelper.FindAll<NTreasureRoomRelicHolder>(room)
                         .Where(h => h.Visible && h.IsEnabled))
            {
                var relic = holder.Relic?.Model;
                var option = NewOption("relic", relic?.Id.ToString() ?? holder.Index.ToString(),
                    relic == null ? "Choose relic" : StateReader.SafeText(() => relic.Title.GetFormattedText()),
                    relic == null ? "" : ReadFormattedProperty(relic, "DynamicDescription", "Description"));
                if (relic != null) option.Relic = ReadRelic(relic);
                Add(state, option, () => Click(holder));
            }
        }
        catch (Exception ex)
        {
            ModLogger.Log($"Treasure relic probe failed: {ex.Message}");
        }

        try { AddNamedClickableChoices(state, room, new[] { "Chest" }); }
        catch (Exception ex) { ModLogger.Log($"Treasure chest probe failed: {ex.Message}"); }
        try { AddProceedButtons(state, room); }
        catch (Exception ex) { ModLogger.Log($"Treasure proceed probe failed: {ex.Message}"); }
        try { AddFallbackClickableChoices(state, room); }
        catch (Exception ex) { ModLogger.Log($"Treasure fallback probe failed: {ex.Message}"); }
        if (state.Options.Count == 0)
            LogTreasureDiagnostics(room);
        return true;
    }

    private static bool BuildGenericChoices(GameStateJson state, Node root, string screenType)
    {
        state.ScreenType = screenType;
        var consumed = new HashSet<Node>();

        foreach (var holder in UiHelper.FindAll<NCardHolder>(root))
        {
            if (holder.CardModel == null) continue;
            consumed.Add(holder.Hitbox);
            var option = NewOption("card", holder.CardModel.Id.ToString(),
                StateReader.SafeText(() => holder.CardModel.Title), "");
            Add(state, option, () =>
            {
                holder.EmitSignal(NCardHolder.SignalName.Pressed, holder);
                return true;
            });
        }

        foreach (var button in UiHelper.FindAll<NClickableControl>(root))
        {
            if (consumed.Contains(button) || !button.Visible || !button.IsEnabled) continue;
            var typeName = button.GetType().Name;
            var nodeName = button.Name.ToString();
            var label = ReadNodeLabel(button);
            if (IsUnsafeAutomationChoice($"{nodeName} {typeName} {label}")) continue;
            if (!IsChoiceLike(typeName, nodeName)) continue;
            var option = NewOption(ChoiceKind(typeName, nodeName), nodeName,
                label, typeName);
            Add(state, option, () => Click(button));
        }
        AddFallbackClickableChoices(state, root, consumed);
        return true;
    }

    /// <summary>未知事件的最后兜底：仅在没有任何已识别选项时暴露作用域内全部可点击控件。</summary>
    private static void AddFallbackClickableChoices(GameStateJson state, Node root, HashSet<Node>? consumed = null)
    {
        if (state.Options.Count > 0) return;
        consumed ??= new HashSet<Node>();
        foreach (var button in UiHelper.FindAll<NClickableControl>(root))
        {
            if (consumed.Contains(button) || !button.Visible || !button.IsEnabled) continue;
            var typeName = button.GetType().Name;
            var nodeName = button.Name.ToString();
            if (IsUnsafeAutomationChoice($"{nodeName} {typeName} {ReadNodeLabel(button)}")) continue;
            Add(state, NewOption("fallback", nodeName, ReadNodeLabel(button),
                $"Unrecognized flow control: {typeName}"), () => Click(button));
        }
    }

    private static void AddNamedClickableChoices(GameStateJson state, Node root, IReadOnlyList<string> names)
    {
        foreach (var button in UiHelper.FindAll<NClickableControl>(root))
        {
            var text = $"{button.Name} {button.GetType().Name}";
            var label = ReadNodeLabel(button);
            if (!button.Visible || !button.IsEnabled
                || IsUnsafeAutomationChoice($"{text} {label}")
                || !names.Any(n => $"{text} {label}".Contains(n, StringComparison.OrdinalIgnoreCase)))
                continue;
            Add(state, NewOption(ChoiceKind(button.GetType().Name, button.Name.ToString()),
                button.Name.ToString(), label, button.GetType().Name), () => Click(button));
        }
    }

    private static void AddProceedButtons(GameStateJson state, Node root)
    {
        foreach (var button in UiHelper.FindAll<NProceedButton>(root).Where(b => b.Visible && b.IsEnabled))
            Add(state, NewOption(button.IsSkip ? "skip" : "proceed", button.Name.ToString(),
                button.IsSkip ? "Skip" : "Proceed", "Continue to the next game state"), () => Click(button));
    }

    private static void PopulateReward(ChoiceOptionJson option, Reward reward)
    {
        var player = GetPlayer();
        switch (reward)
        {
            case GoldReward gold:
                option.Cost = 0;
                option.Description = $"Gain {gold.Amount} gold";
                break;
            case CardReward cardReward:
                option.Description = "Open card reward: " + string.Join(", ", cardReward.Cards.Select(c => StateReader.SafeText(() => c.Title)));
                break;
            case RelicReward relicReward when relicReward.Relic != null:
                option.Relic = ReadRelic(relicReward.Relic);
                break;
            case PotionReward potionReward when potionReward.Potion != null:
                option.Potion = ReadPotion(potionReward.Potion, player);
                break;
        }
    }

    private static void PopulateMerchantOption(ChoiceOptionJson option, MerchantEntry entry)
    {
        var player = GetPlayer();
        if (entry is MerchantCardEntry card && card.CreationResult?.Card != null && player != null)
            option.Card = StateReader.ReadCard(card.CreationResult.Card, player, MegaCrit.Sts2.Core.Entities.Cards.PileType.Deck);
        else if (entry is MerchantRelicEntry relic && relic.Model != null)
            option.Relic = ReadRelic(relic.Model);
        else if (entry is MerchantPotionEntry potion && potion.Model != null)
            option.Potion = ReadPotion(potion.Model, player);
    }

    private static string MerchantName(MerchantEntry entry) => entry switch
    {
        MerchantCardEntry card when card.CreationResult?.Card != null => StateReader.SafeText(() => card.CreationResult.Card.Title),
        MerchantRelicEntry relic when relic.Model != null => StateReader.SafeText(() => relic.Model.Title.GetFormattedText()),
        MerchantPotionEntry potion when potion.Model != null => StateReader.SafeText(() => potion.Model.Title.GetFormattedText()),
        _ => entry.GetType().Name.Replace("Merchant", "").Replace("Entry", "")
    };

    private static string MerchantDescription(MerchantEntry entry) => entry switch
    {
        MerchantCardEntry card when card.CreationResult?.Card != null =>
            StateReader.SafeText(() => card.CreationResult.Card.GetDescriptionForPile(MegaCrit.Sts2.Core.Entities.Cards.PileType.Deck, null)),
        MerchantRelicEntry relic when relic.Model != null => ReadFormattedProperty(relic.Model, "DynamicDescription", "Description"),
        MerchantPotionEntry potion when potion.Model != null => ReadFormattedProperty(potion.Model, "DynamicDescription", "Description"),
        _ => ""
    };

    private static string RewardKind(Reward reward) => reward switch
    {
        CardReward => "card_reward",
        GoldReward => "gold",
        RelicReward => "relic",
        PotionReward => "potion",
        CardRemovalReward => "card_remove",
        _ => "reward"
    };

    private static RelicStateJson ReadRelic(RelicModel relic) => new()
    {
        Id = relic.Id.ToString(),
        Name = StateReader.SafeText(() => relic.Title.GetFormattedText()),
        Counter = ReadInt(relic, "Counter", -1),
    };

    private static PotionStateJson ReadPotion(PotionModel potion, MegaCrit.Sts2.Core.Entities.Players.Player? player) => new()
    {
        Slot = -1,
        Id = potion.Id.ToString(),
        Name = StateReader.SafeText(() => potion.Title.GetFormattedText()),
        TargetType = potion.TargetType.ToString(),
        CanUse = player?.HasOpenPotionSlots ?? false,
        Description = ReadFormattedProperty(potion, "DynamicDescription", "Description"),
    };

    private static MegaCrit.Sts2.Core.Entities.Players.Player? GetPlayer()
    {
        var run = RunManager.Instance.DebugOnlyGetState();
        return run == null ? null : LocalContext.GetMe(run);
    }

    private static Node? GetRoomNode(string name)
    {
        var root = ((SceneTree)Engine.GetMainLoop()).Root;
        return root.GetNodeOrNull($"/root/Game/RootSceneContainer/Run/RoomContainer/{name}");
    }

    private static bool Click(NClickableControl button)
    {
        if (!GodotObject.IsInstanceValid(button) || !button.IsEnabled) return false;
        if (IsUnsafeAutomationChoice($"{button.Name} {button.GetType().Name} {ReadNodeLabel(button)}"))
            return false;
        button.ForceClick();
        return true;
    }

    private static ChoiceOptionJson NewOption(string kind, string id, string name, string description) => new()
    {
        Kind = kind,
        Id = id,
        Name = string.IsNullOrWhiteSpace(name) ? id : name,
        Description = description,
    };

    private static bool IsUnsafeAutomationChoice(string text)
    {
        // 报错/反馈弹窗不是游戏流程动作，自动点击会把崩溃报告页越点越乱。
        return new[]
        {
            "feedback", "report", "bug", "crash", "error",
            "反馈", "报告", "报错", "错误", "崩溃", "提交"
        }.Any(token => text.Contains(token, StringComparison.OrdinalIgnoreCase));
    }

    private static void Add(GameStateJson state, ChoiceOptionJson option, Func<bool> execute)
    {
        option.Index = UiActionRegistry.Register(execute);
        state.Options.Add(option);
    }

    private static bool IsChoiceLike(string typeName, string nodeName)
    {
        var text = typeName + " " + nodeName;
        return new[] { "Button", "Holder", "Hitbox", "Cell", "Bundle", "Proceed", "Skip", "Confirm", "Choice", "Option" }
            .Any(token => text.Contains(token, StringComparison.OrdinalIgnoreCase));
    }

    private static string ChoiceKind(string typeName, string nodeName)
    {
        var text = (typeName + " " + nodeName).ToLowerInvariant();
        if (text.Contains("proceed") || text.Contains("continue")) return "proceed";
        if (text.Contains("skip")) return "skip";
        if (text.Contains("confirm")) return "confirm";
        if (text.Contains("chest")) return "open_chest";
        if (text.Contains("back") || text.Contains("cancel")) return "back";
        return "choice";
    }

    private static string ReadNodeLabel(Node node)
    {
        foreach (var child in EnumerateNodes(node))
        {
            var text = ReadString(child, "Text");
            if (!string.IsNullOrWhiteSpace(text)) return text;
        }
        return node.Name.ToString();
    }

    private static IEnumerable<Node> EnumerateNodes(Node root)
    {
        yield return root;
        foreach (Node child in root.GetChildren())
            foreach (var nested in EnumerateNodes(child))
                yield return nested;
    }

    private static void LogTreasureDiagnostics(Node room)
    {
        if (_loggedTreasureDiagnostics) return;
        _loggedTreasureDiagnostics = true;
        ModLogger.Log($"Treasure diagnostics: room={room.GetType().FullName} name={room.Name}");
        foreach (var method in room.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                     .Where(method => new[] { "chest", "open", "reward", "relic", "click", "press" }
                         .Any(token => method.Name.Contains(token, StringComparison.OrdinalIgnoreCase)))
                     .Take(40))
        {
            ModLogger.Log($"Treasure method: {method.Name} params={method.GetParameters().Length}");
        }
        foreach (var node in EnumerateNodes(room).Take(120))
        {
            var visible = node is CanvasItem canvas ? canvas.Visible.ToString() : "?";
            var enabled = node is NClickableControl clickable ? clickable.IsEnabled.ToString() : "?";
            ModLogger.Log($"Treasure node: {node.GetType().FullName} name={node.Name} visible={visible} enabled={enabled}");
        }
    }

    private static string ReadFormattedProperty(object target, params string[] names)
    {
        foreach (var name in names)
        {
            try
            {
                var value = target.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)?.GetValue(target);
                if (value == null) continue;
                var formatted = value.GetType().GetMethod("GetFormattedText", Type.EmptyTypes)?.Invoke(value, null)?.ToString();
                if (!string.IsNullOrWhiteSpace(formatted)) return formatted;
                if (value is string text && !string.IsNullOrWhiteSpace(text)) return text;
            }
            catch { }
        }
        return "";
    }

    private static string ReadString(object target, string name)
    {
        try { return target.GetType().GetProperty(name)?.GetValue(target)?.ToString() ?? ""; }
        catch { return ""; }
    }

    private static int ReadInt(object target, string name, int fallback)
    {
        try
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            var value = target.GetType().GetProperty(name, flags)?.GetValue(target)
                        ?? target.GetType().GetField(name, flags)?.GetValue(target);
            return value is IConvertible convertible ? Convert.ToInt32(convertible) : fallback;
        }
        catch { return fallback; }
    }

    private static HashSet<object> ReadObjectSet(object target, string fieldName)
    {
        var result = new HashSet<object>(ReferenceEqualityComparer.Instance);
        try
        {
            var field = target.GetType().GetField(fieldName,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (field?.GetValue(target) is System.Collections.IEnumerable values)
                foreach (var value in values)
                    if (value != null) result.Add(value);
        }
        catch { }
        return result;
    }
}

/// <summary>保存最近一次状态快照中 option_index 对应的主线程动作。</summary>
public static class UiActionRegistry
{
    private static readonly List<Func<bool>> Actions = new();

    public static void BeginSnapshot() => Actions.Clear();

    public static int Register(Func<bool> action)
    {
        Actions.Add(action);
        return Actions.Count - 1;
    }

    public static bool Execute(int optionIndex)
    {
        if (optionIndex < 0 || optionIndex >= Actions.Count)
        {
            ModLogger.Log($"Invalid UI option index: {optionIndex} (count={Actions.Count})");
            return false;
        }
        return Actions[optionIndex]();
    }
}
