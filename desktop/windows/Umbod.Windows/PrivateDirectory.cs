using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
namespace Umbod.Windows;
internal static class PrivateDirectory
{
    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes
    {
        public int Length; public IntPtr Descriptor; [MarshalAs(UnmanagedType.Bool)] public bool Inherit;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)][return: MarshalAs(UnmanagedType.Bool)] private static extern bool CreateDirectoryW(string path, ref SecurityAttributes attributes);
    public static void Ensure(string path)
    {
        var full = Path.GetFullPath(path);
        var parent = Path.GetDirectoryName(full);
        if (parent is not null && !Directory.Exists(parent))
            Ensure(parent);
        // Reject every reparse-point ancestor before installing any executable or reading a capability.
        for (var current = new DirectoryInfo(full); current is not null; current = current.Parent)
            if (current.Exists && (current.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Umbod data directories cannot contain symbolic links or junctions.");
        var sid = WindowsIdentity.GetCurrent().User ?? throw new IOException("Cannot determine current Windows account.");
        var acl = new DirectorySecurity();
        acl.SetOwner(sid);
        acl.SetAccessRuleProtection(true, false);
        acl.AddAccessRule(new FileSystemAccessRule(sid, FileSystemRights.FullControl, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit, PropagationFlags.None, AccessControlType.Allow));
        var bytes = acl.GetSecurityDescriptorBinaryForm();
        var pinned = GCHandle.Alloc(bytes, GCHandleType.Pinned);
        try
        {
            var attributes = new SecurityAttributes { Length = Marshal.SizeOf<SecurityAttributes>(), Descriptor = pinned.AddrOfPinnedObject(), Inherit = false };
            if (!CreateDirectoryW(full, ref attributes) && Marshal.GetLastWin32Error() != 183)
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Cannot create private Umbod directory.");
        }
        finally { pinned.Free(); }
        var directory = new DirectoryInfo(full);
        var existing = directory.GetAccessControl(AccessControlSections.Owner | AccessControlSections.Access);
        if (!sid.Equals(existing.GetOwner(typeof(SecurityIdentifier))))
            throw new IOException("Umbod data directory is not owned by the current account.");
        // Existing directories are tightened before any child writes; inherited child access follows this protected parent.
        directory.SetAccessControl(acl);
    }
}
