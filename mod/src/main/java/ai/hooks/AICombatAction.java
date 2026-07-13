package ai.hooks;

import ai.server.AIServer;
import com.megacrit.cardcrawl.actions.AbstractGameAction;
import com.megacrit.cardcrawl.actions.common.EndTurnAction;
import com.megacrit.cardcrawl.cards.CardQueueItem;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.rooms.AbstractRoom;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * An action that waits for AI decisions during combat.
 * Added to the action manager when a player turn starts.
 * Lives for the entire turn, processing one decision at a time.
 */
public class AICombatAction extends AbstractGameAction {

    private static final Logger logger = LogManager.getLogger(AICombatAction.class.getName());
    private static final boolean DEBUG = Boolean.parseBoolean(
            System.getProperty("sts.ai.debug", "false"));

    @Override
    public void update() {
        if (AbstractDungeon.player == null) {
            this.isDone = true;
            return;
        }

        // Check for AI decision
        AIDecision decision = AIServer.pollDecision();

        if (decision == null) {
            return; // No decision yet, wait for next frame
        }

        if (decision.type == AIDecision.Type.END_TURN) {
            logger.info("AI Combat Action: End Turn");
            AbstractDungeon.actionManager.addToBottom(new EndTurnAction());
            this.isDone = true;
            return;
        }

        if (decision.type == AIDecision.Type.PLAY_CARD) {
            int handIdx = decision.handIndex;
            if (handIdx < 0 || handIdx >= AbstractDungeon.player.hand.group.size()) {
                logger.warn("AI Combat Action: Invalid hand index " + handIdx);
                return; // Try again next frame
            }

            var card = AbstractDungeon.player.hand.group.get(handIdx);
            AbstractMonster target = null;

            if (decision.monsterIndex >= 0) {
                var monsters = AbstractDungeon.getMonsters().monsters;
                if (decision.monsterIndex < monsters.size()) {
                    target = monsters.get(decision.monsterIndex);
                }
            }

            if (target == null) {
                // Auto-target first alive monster for attacks
                for (AbstractMonster m : AbstractDungeon.getMonsters().monsters) {
                    if (!m.isDeadOrEscaped()) {
                        target = m;
                        break;
                    }
                }
            }

            logger.info("AI Combat Action: Play " + card.name + " (idx:" + handIdx + ") on " +
                    (target != null ? target.name : "none"));

            // Queue the card play
            AbstractDungeon.actionManager.addCardQueueItem(
                    new CardQueueItem(card, target, card.energyOnUse, true), true
            );
            return; // Don't set isDone - wait for next decision
        }

        if (decision.type == AIDecision.Type.USE_POTION) {
            int slot = decision.potionSlot;
            if (slot >= 0 && slot < AbstractDungeon.player.potions.size()) {
                var potion = AbstractDungeon.player.potions.get(slot);
                if (potion != null) {
                    AbstractMonster target = null;
                    if (decision.monsterIndex >= 0) {
                        var monsters = AbstractDungeon.getMonsters().monsters;
                        if (decision.monsterIndex < monsters.size()) {
                            target = monsters.get(decision.monsterIndex);
                        }
                    }
                    if (target != null) {
                        potion.use(target);
                    } else {
                        // Use on self or random target
                        for (AbstractMonster m : AbstractDungeon.getMonsters().monsters) {
                            if (!m.isDeadOrEscaped()) { target = m; break; }
                        }
                        if (target != null) potion.use(target);
                    }
                    AbstractDungeon.player.potions.set(slot, null);
                }
            }
        }
    }

    // Decision data with inner-class for hook access
    public static class AIDecision {
        public enum Type { PLAY_CARD, END_TURN, USE_POTION }
        public final Type type;
        public final int handIndex;
        public final int monsterIndex;
        public final int potionSlot;

        public AIDecision(Type type, int handIndex, int monsterIndex, int potionSlot) {
            this.type = type;
            this.handIndex = handIndex;
            this.monsterIndex = monsterIndex;
            this.potionSlot = potionSlot;
        }

        public static AIDecision fromJson(String json) {
            return ai.server.AIDecision.fromJson(json);
        }
    }
}
