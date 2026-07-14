using System.Reflection;
using HarmonyLib;
using MegaCrit.Sts2.Core.Modding;

namespace Sts2AiMod;

/// <summary>
/// Mod 入口 — 由 STS2 原生 ModManager 通过 mods/Sts2AiMod/Sts2AiMod.json 加载。
/// </summary>
/// <summary>STS2 原生 Mod 系统入口。</summary>
[ModInitializer(nameof(Initialize))]
public class StartupHook
{
    private static Harmony? _harmony;
    private static AiHttpServer? _httpServer;
    private static readonly object _lock = new();
    private static bool _initialized;

    public static void Initialize()
    {
        if (_initialized) return;
        lock (_lock)
        {
            if (_initialized) return;
            _initialized = true;
        }

        try
        {
            ModLogger.Log("Sts2AiMod initializer executing...");

            // 初始化 Harmony 并修补所有标记的方法
            _harmony = new Harmony("com.sts2.aiagent");
            _harmony.PatchAll(Assembly.GetExecutingAssembly());

            // 启动 HTTP 服务器（后台线程）
            _httpServer = new AiHttpServer(18888);
            _httpServer.Start();

            ModLogger.Log("Sts2AiMod initialized successfully via startup hook");
        }
        catch (Exception ex)
        {
            ModLogger.Log($"Sts2AiMod initialization failed: {ex}");
        }
    }
}
