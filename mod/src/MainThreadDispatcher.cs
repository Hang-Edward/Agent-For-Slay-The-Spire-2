using Godot;

namespace Sts2AiMod;

/// <summary>把 HTTP 后台线程收到的游戏动作切回 Godot 主线程执行。</summary>
public static class MainThreadDispatcher
{
    public static bool Execute(Func<bool> action, int timeoutMs = 5000)
    {
        var context = Dispatcher.SynchronizationContext;
        if (context == null)
        {
            ModLogger.Log("Godot dispatcher synchronization context is not available");
            return false;
        }

        var done = new ManualResetEventSlim(false);
        var result = false;
        Exception? error = null;

        context.Post(_ =>
        {
            try
            {
                result = action();
            }
            catch (Exception ex)
            {
                error = ex;
            }
            finally
            {
                done.Set();
            }
        }, null);

        if (!done.Wait(timeoutMs))
        {
            ModLogger.Log($"Main thread action timed out after {timeoutMs}ms");
            return false;
        }

        if (error != null)
        {
            ModLogger.Log($"Main thread action failed: {error}");
            return false;
        }

        return result;
    }
}
