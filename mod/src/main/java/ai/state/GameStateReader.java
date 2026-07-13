package ai.state;

import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.characters.AbstractPlayer;
import com.megacrit.cardcrawl.core.AbstractCreature;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.potions.AbstractPotion;
import com.megacrit.cardcrawl.relics.AbstractRelic;

import java.util.ArrayList;

/**
 * Reads full game state and serializes to JSON string.
 * No external dependencies - builds JSON manually.
 */
public class GameStateReader {

    public static String readFullState() {
        if (AbstractDungeon.player == null) {
            return "{\"error\":\"player_not_initialized\"}";
        }

        StringBuilder sb = new StringBuilder();
        sb.append("{");

        // Screen type
        sb.append("\"screen_type\":\"").append(escape(AbstractDungeon.screen)).append("\",");
        sb.append("\"in_combat\":").append(AbstractDungeon.getCurrRoom() != null &&
                AbstractDungeon.getCurrRoom().phase == com.megacrit.cardcrawl.rooms.AbstractRoom.RoomPhase.COMBAT).append(",");

        // Player
        AbstractPlayer p = AbstractDungeon.player;
        sb.append("\"player\":{");
        sb.append("\"current_hp\":").append(p.currentHealth).append(",");
        sb.append("\"max_hp\":").append(p.maxHealth).append(",");
        sb.append("\"block\":").append(p.currentBlock).append(",");
        sb.append("\"energy\":").append(p.energy.energy).append(",");
        sb.append("\"energy_this_turn\":").append(p.energy.energyMaster).append(",");
        sb.append("\"gold\":").append(p.gold).append(",");
        sb.append("\"powers\":[");
        boolean first = true;
        for (com.megacrit.cardcrawl.powers.AbstractPower pow : p.powers) {
            if (!first) sb.append(",");
            first = false;
            sb.append("{\"id\":\"").append(escape(pow.ID)).append("\",");
            sb.append("\"name\":\"").append(escape(pow.name)).append("\",");
            sb.append("\"amount\":").append(pow.amount).append("}");
        }
        sb.append("]");
        sb.append("},");

        // Monsters
        sb.append("\"monsters\":[");
        if (AbstractDungeon.getMonsters() != null) {
            ArrayList<AbstractMonster> monsters = AbstractDungeon.getMonsters().monsters;
            first = true;
            for (AbstractMonster m : monsters) {
                if (!first) sb.append(",");
                first = false;
                sb.append(monsterToJson(m));
            }
        }
        sb.append("],");

        // Hand
        sb.append("\"hand\":[");
        first = true;
        for (AbstractCard c : p.hand.group) {
            if (!first) sb.append(",");
            first = false;
            sb.append(cardToJson(c));
        }
        sb.append("],");

        // Draw pile (count only, hidden info)
        sb.append("\"draw_pile_count\":").append(p.drawPile.size()).append(",");

        // Discard pile
        sb.append("\"discard_pile\":[");
        first = true;
        for (AbstractCard c : p.discardPile.group) {
            if (!first) sb.append(",");
            first = false;
            sb.append(cardToJson(c));
        }
        sb.append("],");

        // Exhaust pile
        sb.append("\"exhaust_pile\":[");
        first = true;
        for (AbstractCard c : p.exhaustPile.group) {
            if (!first) sb.append(",");
            first = false;
            sb.append(cardToJson(c));
        }
        sb.append("],");

        // Relics
        sb.append("\"relics\":[");
        first = true;
        for (AbstractRelic r : p.relics) {
            if (!first) sb.append(",");
            first = false;
            sb.append("{\"id\":\"").append(escape(r.relicId)).append("\",");
            sb.append("\"name\":\"").append(escape(r.name)).append("\",");
            sb.append("\"counter\":").append(r.counter).append("}");
        }
        sb.append("],");

        // Potions
        sb.append("\"potions\":[");
        first = true;
        for (AbstractPotion pot : p.potions) {
            if (pot == null) continue;
            if (!first) sb.append(",");
            first = false;
            sb.append("{\"slot\":").append(pot.slot).append(",");
            sb.append("\"id\":\"").append(escape(pot.ID)).append("\",");
            sb.append("\"name\":\"").append(escape(pot.name)).append("\",");
            sb.append("\"can_use\":").append(pot.canUse()).append("}");
        }
        sb.append("],");

        // Turn
        sb.append("\"turn\":").append(AbstractDungeon.actionManager.turn).append(",");

        // Act & Floor
        sb.append("\"act\":").append(AbstractDungeon.actNum).append(",");
        sb.append("\"floor\":").append(AbstractDungeon.floorNum).append(",");

        // Ascension
        sb.append("\"ascension_level\":").append(AbstractDungeon.ascensionLevel).append(",");

        // Character class
        sb.append("\"class\":\"").append(escape(p.getCardClass().name())).append("\"");

        sb.append("}");
        return sb.toString();
    }

    private static String monsterToJson(AbstractMonster m) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"id\":\"").append(escape(m.id)).append("\",");
        sb.append("\"name\":\"").append(escape(m.name)).append("\",");
        sb.append("\"current_hp\":").append(m.currentHealth).append(",");
        sb.append("\"max_hp\":").append(m.maxHealth).append(",");
        sb.append("\"block\":").append(m.currentBlock).append(",");
        sb.append("\"intent\":\"").append(escape(m.intent.name())).append("\",");
        sb.append("\"intent_damage\":").append(m.getIntentDmg()).append(",");
        sb.append("\"intent_hits\":").append(m.getIntentHits()).append(",");
        sb.append("\"is_gone\":").append(m.isDeadOrEscaped()).append(",");
        sb.append("\"half_dead\":").append(m.halfDead).append(",");
        sb.append("\"powers\":[");
        boolean first = true;
        for (com.megacrit.cardcrawl.powers.AbstractPower pow : m.powers) {
            if (!first) sb.append(",");
            first = false;
            sb.append("{\"id\":\"").append(escape(pow.ID)).append("\",");
            sb.append("\"name\":\"").append(escape(pow.name)).append("\",");
            sb.append("\"amount\":").append(pow.amount).append("}");
        }
        sb.append("]");
        sb.append("}");
        return sb.toString();
    }

    private static String cardToJson(AbstractCard c) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"uuid\":\"").append(escape(c.uuid.toString())).append("\",");
        sb.append("\"id\":\"").append(escape(c.cardID)).append("\",");
        sb.append("\"name\":\"").append(escape(c.name)).append("\",");
        sb.append("\"cost\":").append(c.costForTurn).append(",");
        sb.append("\"type\":\"").append(escape(c.type.name())).append("\",");
        sb.append("\"rarity\":\"").append(escape(c.rarity.name())).append("\",");
        sb.append("\"has_target\":").append(c.type == AbstractCard.CardType.ATTACK).append(",");
        sb.append("\"is_playable\":").append(c.hasEnoughEnergy() && c.isPlayable).append(",");
        sb.append("\"upgrades\":").append(c.timesUpgraded).append(",");
        sb.append("\"damage\":").append(c.baseDamage).append(",");
        sb.append("\"block\":").append(c.baseBlock).append(",");
        sb.append("\"magic_number\":").append(c.baseMagicNumber).append(",");
        sb.append("\"exhausts\":").append(c.exhaust).append(",");
        sb.append("\"ethereal\":").append(c.isEthereal).append(",");
        sb.append("\"description\":\"").append(escape(c.rawDescription)).append("\"");
        sb.append("}");
        return sb.toString();
    }

    private static String escape(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
}
