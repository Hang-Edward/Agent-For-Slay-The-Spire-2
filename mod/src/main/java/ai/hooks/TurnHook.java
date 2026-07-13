package ai.hooks;

import basemod.interfaces.OnPlayerTurnStartSubscriber;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.rooms.AbstractRoom;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Hooks into turn lifecycle.
 * When a player turn starts, adds the AI combat action to the queue.
 */
public class TurnHook implements OnPlayerTurnStartSubscriber {

    private static final Logger logger = LogManager.getLogger(TurnHook.class.getName());

    @Override
    public void receiveOnPlayerTurnStart() {
        if (!AbstractDungeon.isPlayerInDungeon()) return;
        if (AbstractDungeon.getCurrRoom() == null) return;
        if (AbstractDungeon.getCurrRoom().phase != AbstractRoom.RoomPhase.COMBAT) return;

        logger.info("TurnHook: Player turn " + AbstractDungeon.actionManager.turn + " started");

        // Add AI combat action to the game's action queue
        // This action will wait for AI decisions throughout the turn
        AbstractDungeon.actionManager.addToBottom(new AICombatAction());
    }
}
