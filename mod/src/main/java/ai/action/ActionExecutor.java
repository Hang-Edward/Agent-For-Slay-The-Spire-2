package ai.action;

import com.megacrit.cardcrawl.actions.AbstractGameAction;
import com.megacrit.cardcrawl.actions.common.EndTurnAction;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.cards.CardQueueItem;
import com.megacrit.cardcrawl.characters.AbstractPlayer;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.potions.AbstractPotion;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Executes AI decisions in the game.
 * All methods must be called from the game thread.
 */
public class ActionExecutor {

    private static final Logger logger = LogManager.getLogger(ActionExecutor.class.getName());

    /**
     * Queue a card to be played. The card will be processed through the
     * game's normal card queue system (handles energy cost, triggers, etc.).
     */
    public static void playCard(int handIndex, int monsterIndex) {
        AbstractPlayer p = AbstractDungeon.player;
        if (handIndex < 0 || handIndex >= p.hand.group.size()) {
            logger.warn("Invalid hand index: " + handIndex);
            return;
        }

        AbstractCard card = p.hand.group.get(handIndex);
        AbstractMonster target = null;

        if (monsterIndex >= 0) {
            var monsters = AbstractDungeon.getMonsters().monsters;
            if (monsterIndex < monsters.size()) {
                target = monsters.get(monsterIndex);
            }
        }

        // If card needs a target but none specified, pick the first alive monster
        if (card.type == AbstractCard.CardType.ATTACK && target == null) {
            for (AbstractMonster m : AbstractDungeon.getMonsters().monsters) {
                if (!m.isDeadOrEscaped()) {
                    target = m;
                    break;
                }
            }
        }

        logger.info("AI plays: " + card.name + " (cost:" + card.costForTurn + ") -> " +
                (target != null ? target.name : "none"));

        // Queue the card through the game's card queue system
        AbstractDungeon.actionManager.addCardQueueItem(
                new CardQueueItem(card, target, card.energyOnUse, true), true
        );
    }

    /**
     * End the current turn.
     */
    public static void endTurn() {
        logger.info("AI ends turn.");
        AbstractDungeon.actionManager.addToBottom(new EndTurnAction());
    }

    /**
     * Use a potion on a target.
     */
    public static void usePotion(int slot, int targetIndex) {
        AbstractPlayer p = AbstractDungeon.player;
        if (slot < 0 || slot >= p.potions.size() || p.potions.get(slot) == null) {
            logger.warn("Invalid potion slot: " + slot);
            return;
        }

        AbstractMonster target = null;
        if (targetIndex >= 0) {
            var monsters = AbstractDungeon.getMonsters().monsters;
            if (targetIndex < monsters.size()) {
                target = monsters.get(targetIndex);
            }
        }

        AbstractPotion potion = p.potions.get(slot);
        logger.info("AI uses potion: " + potion.name);

        if (target != null) {
            potion.use(target);
        } else {
            potion.use(AbstractDungeon.player);
        }

        // Remove the potion after use
        p.potions.set(slot, null);
    }
}
