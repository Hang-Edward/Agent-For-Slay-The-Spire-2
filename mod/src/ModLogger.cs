namespace Sts2AiMod;

/// <summary>简单日志记录器。</summary>
public static class ModLogger
{
    private static readonly string LogPath = Path.Combine(
        AppDomain.CurrentDomain.BaseDirectory,
        "..", "sts_ai_mod_log.txt");

    static ModLogger()
    {
        try
        {
            var dir = Path.GetDirectoryName(LogPath);
            if (dir != null) Directory.CreateDirectory(dir);
            File.AppendAllText(LogPath, $"\n=== Sts2AiMod started at {DateTime.Now:yyyy-MM-dd HH:mm:ss} ===\n");
        }
        catch { }
    }

    public static void Log(string message)
    {
        var line = $"[{DateTime.Now:HH:mm:ss}] {message}";
        try
        {
            File.AppendAllText(LogPath, line + "\n");
        }
        catch { }
        System.Diagnostics.Debug.WriteLine(line);
    }
}
