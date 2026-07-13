package ai.server;

import ai.state.GameStateReader;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.sun.net.httpserver.HttpServer;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class AIServer {

    private static final Logger logger = LogManager.getLogger(AIServer.class.getName());
    private static HttpServer server;
    private static final BlockingQueue<AIDecision> decisionQueue = new LinkedBlockingQueue<>();
    private static final AtomicBoolean inBattle = new AtomicBoolean(false);
    private static final AtomicBoolean awaitingDecision = new AtomicBoolean(false);

    public static void start(int port) {
        try {
            server = HttpServer.create(new InetSocketAddress(port), 0);
            server.createContext("/state", exchange -> {
                String json = GameStateReader.readFullState();
                byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
                exchange.close();
            });

            server.createContext("/decision", exchange -> {
                if (!"POST".equals(exchange.getRequestMethod())) {
                    exchange.sendResponseHeaders(405, -1);
                    exchange.close();
                    return;
                }
                String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                AIDecision decision = AIDecision.fromJson(body);
                decisionQueue.offer(decision);
                awaitingDecision.set(false);

                String resp = "{\"status\":\"ok\"}";
                byte[] bytes = resp.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
                exchange.close();
                logger.info("Received decision: " + body);
            });

            server.createContext("/status", exchange -> {
                String status = String.format(
                    "{\"in_battle\":%b,\"awaiting_decision\":%b,\"in_game\":%b}",
                    inBattle.get(), awaitingDecision.get(),
                    AbstractDungeon.player != null
                );
                byte[] bytes = status.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
                exchange.close();
            });

            server.setExecutor(java.util.concurrent.Executors.newFixedThreadPool(2));
            server.start();
            logger.info("HTTP server started on port " + port);
        } catch (Exception e) {
            logger.error("Failed to start HTTP server", e);
        }
    }

    public static AIDecision pollDecision() {
        return decisionQueue.poll();
    }

    public static boolean isAwaitingDecision() {
        return awaitingDecision.get();
    }

    public static void setAwaitingDecision(boolean v) {
        awaitingDecision.set(v);
    }

    public static void onBattleStart() {
        inBattle.set(true);
        decisionQueue.clear();
        logger.info("AI: Battle started");
    }

    public static void onBattleEnd() {
        inBattle.set(false);
        awaitingDecision.set(false);
        decisionQueue.clear();
        logger.info("AI: Battle ended");
    }

    public static boolean isInBattle() {
        return inBattle.get();
    }
}
