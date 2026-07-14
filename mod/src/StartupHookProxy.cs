using System.Reflection;

/// <summary>
/// .NET 启动钩子入口必须暴露为全局 StartupHook.Initialize()。
/// 这里先写入探针日志，再转发到真正的 Mod 初始化逻辑。
/// </summary>
public static class StartupHook
{
    public static void Initialize()
    {
        var hookDir = Path.GetDirectoryName(typeof(StartupHook).Assembly.Location)
            ?? AppContext.BaseDirectory;
        var probeLog = Path.Combine(hookDir, "sts_ai_startup_hook_probe.txt");

        void Probe(string message)
        {
            try
            {
                File.AppendAllText(
                    probeLog,
                    $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}{Environment.NewLine}"
                );
            }
            catch
            {
                // 启动钩子不能因为日志失败而阻止游戏启动。
            }
        }

        Probe("Global StartupHook.Initialize entered.");

        AppDomain.CurrentDomain.AssemblyResolve += (_, args) =>
        {
            var assemblyName = new AssemblyName(args.Name).Name + ".dll";
            var localPath = Path.Combine(hookDir, assemblyName);
            if (File.Exists(localPath))
            {
                Probe($"Resolving dependency from hook dir: {assemblyName}");
                return Assembly.LoadFrom(localPath);
            }

            var basePath = Path.Combine(AppContext.BaseDirectory, assemblyName);
            if (File.Exists(basePath))
            {
                Probe($"Resolving dependency from base dir: {assemblyName}");
                return Assembly.LoadFrom(basePath);
            }

            return null;
        };

        try
        {
            Sts2AiMod.StartupHook.Initialize();
            Probe("Sts2AiMod.StartupHook.Initialize completed.");
        }
        catch (Exception ex)
        {
            Probe($"Sts2AiMod.StartupHook.Initialize failed: {ex}");
        }
    }
}
