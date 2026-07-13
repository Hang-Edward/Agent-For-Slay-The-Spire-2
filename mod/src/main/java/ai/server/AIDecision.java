package ai.server;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class AIDecision {
    public enum Type { PLAY_CARD, END_TURN, USE_POTION }

    public final Type type;
    public final int handIndex;
    public final int monsterIndex;
    public final int potionSlot;

    private AIDecision(Type type, int handIndex, int monsterIndex, int potionSlot) {
        this.type = type;
        this.handIndex = handIndex;
        this.monsterIndex = monsterIndex;
        this.potionSlot = potionSlot;
    }

    public static AIDecision playCard(int handIndex, int monsterIndex) {
        return new AIDecision(Type.PLAY_CARD, handIndex, monsterIndex, -1);
    }

    public static AIDecision endTurn() {
        return new AIDecision(Type.END_TURN, -1, -1, -1);
    }

    public static AIDecision usePotion(int slot, int target) {
        return new AIDecision(Type.USE_POTION, -1, target, slot);
    }

    /**
     * Parse from JSON string.
     * Accepts: {"type":"play_card","hand_index":0,"monster_index":0}
     *          {"type":"end_turn"}
     *          {"type":"use_potion","potion_slot":0,"monster_index":0}
     * Also accepts LLM format: PLAY 0 0  or  END
     */
    public static AIDecision fromJson(String json) {
        json = json.trim();

        // Try LLM shorthand format: PLAY <hand> <monster> or END
        if (!json.startsWith("{")) {
            if (json.startsWith("PLAY")) {
                String[] parts = json.split("\\s+");
                int handIdx = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
                int monIdx = parts.length > 2 ? Integer.parseInt(parts[2]) : -1;
                if (monIdx < 0) monIdx = 0;
                return playCard(handIdx, monIdx);
            } else if (json.startsWith("END")) {
                return endTurn();
            } else if (json.startsWith("POTION")) {
                String[] parts = json.split("\\s+");
                int slot = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
                int target = parts.length > 2 ? Integer.parseInt(parts[2]) : 0;
                return usePotion(slot, target);
            }
        }

        // Parse JSON format
        String typeStr = extractString(json, "type");
        if ("end_turn".equals(typeStr)) {
            return endTurn();
        } else if ("play_card".equals(typeStr)) {
            int handIdx = extractInt(json, "hand_index");
            int monIdx = extractInt(json, "monster_index");
            return playCard(handIdx, monIdx);
        } else if ("use_potion".equals(typeStr)) {
            int slot = extractInt(json, "potion_slot");
            int target = extractInt(json, "monster_index");
            return usePotion(slot, target);
        }

        return endTurn();
    }

    private static String extractString(String json, String key) {
        Pattern p = Pattern.compile("\"" + key + "\"\\s*:\\s*\"([^\"]+)\"");
        Matcher m = p.matcher(json);
        return m.find() ? m.group(1) : "";
    }

    private static int extractInt(String json, String key) {
        Pattern p = Pattern.compile("\"" + key + "\"\\s*:\\s*(-?\\d+)");
        Matcher m = p.matcher(json);
        return m.find() ? Integer.parseInt(m.group(1)) : 0;
    }
}
