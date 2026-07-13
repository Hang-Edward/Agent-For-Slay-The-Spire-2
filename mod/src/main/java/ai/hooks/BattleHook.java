package ai.hooks;

import ai.server.AIServer;
import basemod.interfaces.OnPlayerTurnStartSubscriber;
import basemod.interfaces.OnStartBattleSubscriber;
import basemod.interfaces.PostBattleSubscriber;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.rooms.AbstractRoom;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Hooks into battle lifecycle events.
 */
public class BattleHook implements OnStartBattleSubscriber, PostBattleSubscriber {

    private static final Logger logger = LogManager.getLogger(BattleHook.class.getName());

    @Override
    public void receiveOnStartBattle() {
        logger.info("BattleHook: Battle started");
        AIServer.onBattleStart();
    }

    @Override
    public void receivePostBattle(AbstractRoom room) {
        logger.info("BattleHook: Battle ended");
        AIServer.onBattleEnd();
    }
}
