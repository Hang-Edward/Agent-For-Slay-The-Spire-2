using System.Text.Json.Serialization;

namespace Sts2AiMod;

/// <summary>AI 决策数据模型，匹配 Python 端期待的格式。</summary>
public class AiDecision
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = "end_turn";

    [JsonPropertyName("hand_index")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public int HandIndex { get; set; } = -1;

    [JsonPropertyName("monster_index")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public int MonsterIndex { get; set; } = -1;

    [JsonPropertyName("potion_slot")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public int PotionSlot { get; set; } = -1;

    [JsonPropertyName("card_index")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public int CardIndex { get; set; } = -1;

    [JsonPropertyName("option_index")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public int OptionIndex { get; set; } = -1;
}

/// <summary>状态端点响应。</summary>
public class StatusResponse
{
    [JsonPropertyName("in_battle")] public bool InBattle { get; set; }
    [JsonPropertyName("awaiting_decision")] public bool AwaitingDecision { get; set; }
    [JsonPropertyName("action_in_flight")] public bool ActionInFlight { get; set; }
    [JsonPropertyName("state_revision")] public long StateRevision { get; set; }
    [JsonPropertyName("in_game")] public bool InGame { get; set; }
}

/// <summary>游戏状态 JSON（与 Python 端 GameState 格式对齐）。</summary>
public class GameStateJson
{
    [JsonPropertyName("screen_type")] public string ScreenType { get; set; } = "IDLE";
    [JsonPropertyName("room_type")] public string RoomType { get; set; } = "";
    [JsonPropertyName("in_combat")] public bool InCombat { get; set; }
    [JsonPropertyName("decision_ready")] public bool DecisionReady { get; set; }
    [JsonPropertyName("action_in_flight")] public bool ActionInFlight { get; set; }
    [JsonPropertyName("action_in_progress")] public bool ActionInProgress { get; set; }
    [JsonPropertyName("state_revision")] public long StateRevision { get; set; }

    [JsonPropertyName("player")] public PlayerStateJson Player { get; set; } = new();
    [JsonPropertyName("monsters")] public List<MonsterStateJson> Monsters { get; set; } = new();
    [JsonPropertyName("hand")] public List<CardStateJson> Hand { get; set; } = new();
    [JsonPropertyName("deck")] public List<CardStateJson> Deck { get; set; } = new();
    [JsonPropertyName("options")] public List<ChoiceOptionJson> Options { get; set; } = new();
    [JsonPropertyName("teammates")] public List<TeammateStateJson> Teammates { get; set; } = new();
    [JsonPropertyName("team_actions")] public List<TeamActionJson> TeamActions { get; set; } = new();
    [JsonPropertyName("map")] public MapGraphJson Map { get; set; } = new();

    [JsonPropertyName("draw_pile_count")] public int DrawPileCount { get; set; }
    [JsonPropertyName("discard_pile")] public List<CardStateJson> DiscardPile { get; set; } = new();
    [JsonPropertyName("exhaust_pile")] public List<CardStateJson> ExhaustPile { get; set; } = new();

    [JsonPropertyName("relics")] public List<RelicStateJson> Relics { get; set; } = new();
    [JsonPropertyName("potions")] public List<PotionStateJson> Potions { get; set; } = new();

    [JsonPropertyName("turn")] public int Turn { get; set; }
    [JsonPropertyName("act")] public int Act { get; set; }
    [JsonPropertyName("floor")] public int Floor { get; set; }
    [JsonPropertyName("ascension_level")] public int AscensionLevel { get; set; }
    [JsonPropertyName("class")] public string CharClass { get; set; } = "";
}

/// <summary>完整地图 DAG，供路线评分器比较后续房间分布。</summary>
public class MapGraphJson
{
    [JsonPropertyName("current_node_id")] public string CurrentNodeId { get; set; } = "";
    [JsonPropertyName("nodes")] public List<MapNodeJson> Nodes { get; set; } = new();
}

public class MapNodeJson
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("row")] public int Row { get; set; }
    [JsonPropertyName("column")] public int Column { get; set; }
    [JsonPropertyName("type")] public string Type { get; set; } = "";
    [JsonPropertyName("children")] public List<string> Children { get; set; } = new();
    [JsonPropertyName("visited")] public bool Visited { get; set; }
}

/// <summary>不泄露队友手牌内容，只暴露协作所需的公开战斗状态。</summary>
public class TeammateStateJson
{
    [JsonPropertyName("net_id")] public string NetId { get; set; } = "";
    [JsonPropertyName("character")] public string Character { get; set; } = "";
    [JsonPropertyName("current_hp")] public int CurrentHp { get; set; }
    [JsonPropertyName("max_hp")] public int MaxHp { get; set; }
    [JsonPropertyName("block")] public int Block { get; set; }
    [JsonPropertyName("energy")] public int Energy { get; set; }
    [JsonPropertyName("hand_count")] public int HandCount { get; set; }
    [JsonPropertyName("turn")] public int Turn { get; set; }
    [JsonPropertyName("phase")] public string Phase { get; set; } = "None";
    [JsonPropertyName("is_alive")] public bool IsAlive { get; set; }
    [JsonPropertyName("powers")] public List<PowerStateJson> Powers { get; set; } = new();
}

public class TeamActionJson
{
    [JsonPropertyName("actor_net_id")] public string ActorNetId { get; set; } = "";
    [JsonPropertyName("actor")] public string Actor { get; set; } = "";
    [JsonPropertyName("description")] public string Description { get; set; } = "";
    [JsonPropertyName("is_local")] public bool IsLocal { get; set; }
}

/// <summary>所有非战斗界面统一使用的可执行选项。</summary>
public class ChoiceOptionJson
{
    [JsonPropertyName("index")] public int Index { get; set; }
    [JsonPropertyName("kind")] public string Kind { get; set; } = "choice";
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("description")] public string Description { get; set; } = "";
    [JsonPropertyName("enabled")] public bool Enabled { get; set; } = true;
    [JsonPropertyName("cost")] public int Cost { get; set; } = -1;
    [JsonPropertyName("selected")] public bool Selected { get; set; }
    [JsonPropertyName("row")] public int Row { get; set; } = -1;
    [JsonPropertyName("column")] public int Column { get; set; } = -1;
    [JsonPropertyName("card")] public CardStateJson? Card { get; set; }
    [JsonPropertyName("relic")] public RelicStateJson? Relic { get; set; }
    [JsonPropertyName("potion")] public PotionStateJson? Potion { get; set; }
}

public class PlayerStateJson
{
    [JsonPropertyName("current_hp")] public int CurrentHp { get; set; }
    [JsonPropertyName("max_hp")] public int MaxHp { get; set; }
    [JsonPropertyName("block")] public int Block { get; set; }
    [JsonPropertyName("energy")] public int Energy { get; set; }
    [JsonPropertyName("energy_this_turn")] public int EnergyThisTurn { get; set; }
    [JsonPropertyName("max_energy")] public int MaxEnergy { get; set; }
    [JsonPropertyName("gold")] public int Gold { get; set; }
    [JsonPropertyName("phase")] public string Phase { get; set; } = "None";
    [JsonPropertyName("powers")] public List<PowerStateJson> Powers { get; set; } = new();
}

public class MonsterStateJson
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("current_hp")] public int CurrentHp { get; set; }
    [JsonPropertyName("max_hp")] public int MaxHp { get; set; }
    [JsonPropertyName("block")] public int Block { get; set; }
    [JsonPropertyName("intent")] public string Intent { get; set; } = "";
    [JsonPropertyName("intent_damage")] public int IntentDamage { get; set; }
    [JsonPropertyName("intent_hits")] public int IntentHits { get; set; }
    [JsonPropertyName("is_gone")] public bool IsGone { get; set; }
    [JsonPropertyName("targetable")] public bool Targetable { get; set; }
    [JsonPropertyName("target_index")] public int TargetIndex { get; set; } = -1;
    [JsonPropertyName("powers")] public List<PowerStateJson> Powers { get; set; } = new();
}

public class CardStateJson
{
    [JsonPropertyName("uuid")] public string Uuid { get; set; } = "";
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("cost")] public int Cost { get; set; }
    [JsonPropertyName("cost_for_turn")] public int CostForTurn { get; set; }
    [JsonPropertyName("type")] public string CardType { get; set; } = "";
    [JsonPropertyName("rarity")] public string Rarity { get; set; } = "";
    [JsonPropertyName("target_type")] public string TargetType { get; set; } = "";
    [JsonPropertyName("has_target")] public bool HasTarget { get; set; }
    [JsonPropertyName("is_playable")] public bool IsPlayable { get; set; }
    [JsonPropertyName("playable_reason")] public string PlayableReason { get; set; } = "";
    [JsonPropertyName("upgrades")] public int Upgrades { get; set; }
    [JsonPropertyName("damage")] public int Damage { get; set; }
    [JsonPropertyName("block")] public int Block { get; set; }
    [JsonPropertyName("magic_number")] public int MagicNumber { get; set; }
    [JsonPropertyName("exhausts")] public bool Exhausts { get; set; }
    [JsonPropertyName("ethereal")] public bool Ethereal { get; set; }
    [JsonPropertyName("description")] public string Description { get; set; } = "";
}

public class PowerStateJson
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("amount")] public int Amount { get; set; }
}

public class RelicStateJson
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("counter")] public int Counter { get; set; } = -1;
}

public class PotionStateJson
{
    [JsonPropertyName("slot")] public int Slot { get; set; }
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("target_type")] public string TargetType { get; set; } = "";
    [JsonPropertyName("can_use")] public bool CanUse { get; set; }
    [JsonPropertyName("description")] public string Description { get; set; } = "";
}
