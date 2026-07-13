package ai;

import ai.hooks.BattleHook;
import ai.hooks.TurnHook;
import ai.server.AIServer;
import basemod.BaseMod;
import basemod.interfaces.PostInitializeSubscriber;
import com.evacipated.cardcrawl.modthespire.lib.SpireInitializer;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

@SpireInitializer
public class SpireAIMod implements PostInitializeSubscriber {

    public static final Logger logger = LogManager.getLogger(SpireAIMod.class.getName());
    public static final int DEFAULT_PORT = 18888;
    public static int serverPort = DEFAULT_PORT;

    public static void initialize() {
        logger.info("SpireAIMod initializing...");
        SpireAIMod mod = new SpireAIMod();
        BaseMod.subscribe(mod);
    }

    @Override
    public void receivePostInitialize() {
        logger.info("SpireAIMod post-initialize: starting HTTP server on port " + serverPort);
        AIServer.start(serverPort);
        BaseMod.subscribe(new BattleHook());
        BaseMod.subscribe(new TurnHook());
        logger.info("SpireAIMod fully initialized.");
    }
}
