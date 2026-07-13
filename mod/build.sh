#!/bin/bash
# Build script for SpireAIMod
#
# Prerequisites:
#   1. ModTheSpire.jar and BaseMod.jar from Steam Workshop in mod/libs/
#   2. The game's desktop-1.0.jar (from SlayTheSpire/ directory)
#   3. Java 8+ (ModTheSpire requires Java 8)
#
# Usage:
#   ./build.sh                    # Build the mod
#   ./build.sh install            # Build and copy to SlayTheSpire/mods/
#   ./build.sh clean              # Clean build artifacts

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MOD_DIR="$SCRIPT_DIR"
BUILD_DIR="$MOD_DIR/build"
SRC_DIR="$MOD_DIR/src/main/java"
LIBS_DIR="$MOD_DIR/libs"
JAR_NAME="sts-ai-agent.jar"

# Try to find the game installation
GAME_PATH=""
if [ -d "/Applications/SlayTheSpire.app" ]; then
    GAME_PATH="/Applications/SlayTheSpire.app/Contents/Resources"
elif [ -d "$HOME/Library/Application Support/Steam/steamapps/common/SlayTheSpire" ]; then
    GAME_PATH="$HOME/Library/Application Support/Steam/steamapps/common/SlayTheSpire"
elif [ -d "C:/Program Files (x86)/Steam/steamapps/common/SlayTheSpire" ]; then
    GAME_PATH="C:/Program Files (x86)/Steam/steamapps/common/SlayTheSpire"
fi

# Build classpath
CLASSPATH=""
if [ -f "$LIBS_DIR/ModTheSpire.jar" ]; then
    CLASSPATH="$LIBS_DIR/ModTheSpire.jar"
fi
if [ -f "$LIBS_DIR/BaseMod.jar" ]; then
    CLASSPATH="$CLASSPATH:$LIBS_DIR/BaseMod.jar"
fi
if [ -f "$LIBS_DIR/desktop-1.0.jar" ]; then
    CLASSPATH="$CLASSPATH:$LIBS_DIR/desktop-1.0.jar"
elif [ -n "$GAME_PATH" ] && [ -f "$GAME_PATH/desktop-1.0.jar" ]; then
    CLASSPATH="$CLASSPATH:$GAME_PATH/desktop-1.0.jar"
    echo "Found game at: $GAME_PATH"
fi

if [ -z "$CLASSPATH" ]; then
    echo "ERROR: No dependencies found!"
    echo "Please place the following jars in $LIBS_DIR:"
    echo "  - ModTheSpire.jar (from Steam Workshop)"
    echo "  - BaseMod.jar (from Steam Workshop)"
    echo "  - desktop-1.0.jar (from SlayTheSpire installation)"
    exit 1
fi

case "${1:-build}" in
    clean)
        echo "Cleaning build directory..."
        rm -rf "$BUILD_DIR"
        echo "Done."
        exit 0
        ;;
    build|install)
        echo "Building SpireAIMod..."
        rm -rf "$BUILD_DIR"
        mkdir -p "$BUILD_DIR"

        # Find Java files
        JAVA_FILES=$(find "$SRC_DIR" -name "*.java")

        # Compile
        javac -d "$BUILD_DIR" -cp "$CLASSPATH" $JAVA_FILES

        # Copy resources
        if [ -d "$MOD_DIR/src/main/resources" ]; then
            cp -r "$MOD_DIR/src/main/resources/"* "$BUILD_DIR/"
        fi

        # Package into jar
        cd "$BUILD_DIR"
        jar cf "$MOD_DIR/$JAR_NAME" .
        cd "$SCRIPT_DIR"

        echo "Build complete: $MOD_DIR/$JAR_NAME"

        if [ "$1" = "install" ] && [ -n "$GAME_PATH" ]; then
            MODS_DIR="$GAME_PATH/mods"
            if [ -d "$MODS_DIR" ]; then
                cp "$MOD_DIR/$JAR_NAME" "$MODS_DIR/"
                echo "Installed to $MODS_DIR/$JAR_NAME"
            else
                echo "WARNING: Mods directory not found at $MODS_DIR"
            fi
        fi
        ;;
    *)
        echo "Usage: $0 [build|install|clean]"
        exit 1
        ;;
esac
