//! OS security boundary. Private objects are protected before any bytes are written.
use std::{fs::File, io::Write, path::Path};

pub fn private_dir(path: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
        std::fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(path)?;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))
    }
    #[cfg(windows)]
    {
        windows::directory(path)
    }
}
pub fn private_file(path: &Path, new: bool) -> std::io::Result<File> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        std::fs::OpenOptions::new()
            .write(true)
            .create(!new)
            .create_new(new)
            .mode(0o600)
            .open(path)
    }
    #[cfg(windows)]
    {
        windows::file(path, new)
    }
}
pub fn replace(source: &Path, destination: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        std::fs::rename(source, destination)
    }
    #[cfg(windows)]
    {
        windows::replace(source, destination)
    }
}
pub fn atomic_write(path: &Path, bytes: &[u8]) -> std::io::Result<()> {
    let temp = path.with_file_name(format!(".umbod-{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| {
        let mut file = private_file(&temp, true)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        drop(file);
        replace(&temp, path)
    })();
    let _ = std::fs::remove_file(temp);
    result
}
pub fn owner_lock(directory: &Path) -> anyhow::Result<File> {
    let file = private_file(&directory.join("owner.lock"), false)?;
    file.try_lock().map_err(|_| {
        anyhow::anyhow!(
            "Umbod is already running for this data directory. Stop the existing gateway first."
        )
    })?;
    Ok(file)
}
pub fn validate_executable(path: &Path) -> anyhow::Result<()> {
    anyhow::ensure!(
        path.is_absolute() && path.is_file(),
        "Choose an existing absolute executable path"
    );
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        anyhow::ensure!(
            path.metadata()?.permissions().mode() & 0o111 != 0,
            "Selected file is not executable"
        );
    }
    #[cfg(windows)]
    {
        anyhow::ensure!(
            path.extension()
                .and_then(|e| e.to_str())
                .is_some_and(|e| e.eq_ignore_ascii_case("exe")),
            "Choose a native .exe executable. Batch wrappers (.cmd/.bat) are not supported; select node.exe or the provider's .exe and pass the script as an argument."
        );
        validate_windows_image(path)?;
    }
    Ok(())
}
pub fn subprocess_environment(command: &mut tokio::process::Command) {
    command.env_clear();
    #[cfg(unix)]
    {
        command.env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin");
        if let Some(home) = std::env::var_os("HOME") {
            command.env("HOME", home);
        }
    }
    #[cfg(windows)]
    {
        // Never inherit PATH, COMSPEC, PATHEXT, loader hooks or arbitrary secrets.
        for key in [
            "SystemRoot",
            "WINDIR",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
            "TEMP",
            "TMP",
        ] {
            if let Some(value) = std::env::var_os(key) {
                command.env(key, value);
            }
        }
        if let Some(root) = std::env::var_os("SystemRoot") {
            command.env("PATH", Path::new(&root).join("System32"));
        }
    }
}

#[cfg(windows)]
mod windows {
    use super::*;
    use std::{
        ffi::c_void,
        os::windows::{ffi::OsStrExt, io::FromRawHandle},
        ptr,
    };
    type Handle = *mut c_void;
    #[repr(C)]
    struct SecurityAttributes {
        length: u32,
        descriptor: *mut c_void,
        inherit: i32,
    }
    #[repr(C)]
    struct TokenUser {
        sid: *mut c_void,
        attributes: u32,
    }
    #[link(name = "advapi32")]
    unsafe extern "system" {
        fn OpenProcessToken(process: Handle, access: u32, token: *mut Handle) -> i32;
        fn GetTokenInformation(
            token: Handle,
            class: u32,
            data: *mut c_void,
            length: u32,
            needed: *mut u32,
        ) -> i32;
        fn ConvertSidToStringSidW(sid: *mut c_void, text: *mut *mut u16) -> i32;
        fn ConvertStringSecurityDescriptorToSecurityDescriptorW(
            text: *const u16,
            revision: u32,
            descriptor: *mut *mut c_void,
            size: *mut u32,
        ) -> i32;
        fn SetFileSecurityW(path: *const u16, information: u32, descriptor: *mut c_void) -> i32;
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetCurrentProcess() -> Handle;
        fn CloseHandle(handle: Handle) -> i32;
        fn LocalFree(memory: *mut c_void) -> *mut c_void;
        fn CreateDirectoryW(path: *const u16, security: *const SecurityAttributes) -> i32;
        fn CreateFileW(
            path: *const u16,
            access: u32,
            share: u32,
            security: *const SecurityAttributes,
            disposition: u32,
            flags: u32,
            template: Handle,
        ) -> Handle;
        fn MoveFileExW(from: *const u16, to: *const u16, flags: u32) -> i32;
    }
    fn wide(path: &Path) -> Vec<u16> {
        path.as_os_str().encode_wide().chain(Some(0)).collect()
    }
    fn check(ok: i32) -> std::io::Result<()> {
        if ok == 0 {
            Err(std::io::Error::last_os_error())
        } else {
            Ok(())
        }
    }
    struct Descriptor(*mut c_void);
    impl Drop for Descriptor {
        fn drop(&mut self) {
            unsafe {
                LocalFree(self.0);
            }
        }
    }
    impl Descriptor {
        fn current_user() -> std::io::Result<Self> {
            unsafe {
                let mut token = ptr::null_mut();
                check(OpenProcessToken(GetCurrentProcess(), 8, &mut token))?;
                let mut size = 0;
                GetTokenInformation(token, 1, ptr::null_mut(), 0, &mut size);
                // usize backing ensures TOKEN_USER alignment.
                let mut data = vec![0usize; (size as usize).div_ceil(std::mem::size_of::<usize>())];
                let result = check(GetTokenInformation(
                    token,
                    1,
                    data.as_mut_ptr().cast(),
                    size,
                    &mut size,
                ));
                CloseHandle(token);
                result?;
                let user = &*data.as_ptr().cast::<TokenUser>();
                let mut text = ptr::null_mut();
                check(ConvertSidToStringSidW(user.sid, &mut text))?;
                let mut length = 0;
                while *text.add(length) != 0 {
                    length += 1;
                }
                let sid = String::from_utf16_lossy(std::slice::from_raw_parts(text, length));
                LocalFree(text.cast());
                let sddl: Vec<u16> = format!("D:P(A;OICI;FA;;;{sid})")
                    .encode_utf16()
                    .chain(Some(0))
                    .collect();
                let mut descriptor = ptr::null_mut();
                check(ConvertStringSecurityDescriptorToSecurityDescriptorW(
                    sddl.as_ptr(),
                    1,
                    &mut descriptor,
                    ptr::null_mut(),
                ))?;
                Ok(Self(descriptor))
            }
        }
        fn attributes(&self) -> SecurityAttributes {
            SecurityAttributes {
                length: std::mem::size_of::<SecurityAttributes>() as u32,
                descriptor: self.0,
                inherit: 0,
            }
        }
        fn protect(&self, path: &Path) -> std::io::Result<()> {
            unsafe { check(SetFileSecurityW(wide(path).as_ptr(), 0x80000004, self.0)) }
        }
    }
    fn reject_reparse(path: &Path) -> std::io::Result<()> {
        use std::os::windows::fs::MetadataExt;
        for ancestor in path.ancestors() {
            match std::fs::symlink_metadata(ancestor) {
                Ok(meta) if meta.file_attributes() & 0x400 != 0 => {
                    return Err(std::io::Error::other(
                        "Reparse points are not supported for private storage",
                    ));
                }
                Ok(_) => {}
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                Err(e) => return Err(e),
            }
        }
        Ok(())
    }
    pub fn directory(path: &Path) -> std::io::Result<()> {
        reject_reparse(path)?;
        let descriptor = Descriptor::current_user()?;
        if path.exists() {
            return descriptor.protect(path);
        }
        if let Some(parent) = path.parent().filter(|p| !p.exists()) {
            directory(parent)?;
        }
        unsafe {
            check(CreateDirectoryW(
                wide(path).as_ptr(),
                &descriptor.attributes(),
            ))
        }
    }
    pub fn file(path: &Path, new: bool) -> std::io::Result<File> {
        reject_reparse(path)?;
        let descriptor = Descriptor::current_user()?;
        if !new && path.exists() {
            descriptor.protect(path)?;
        }
        let handle = unsafe {
            CreateFileW(
                wide(path).as_ptr(),
                0xc0000000,
                7,
                &descriptor.attributes(),
                if new { 1 } else { 4 },
                0x80,
                ptr::null_mut(),
            )
        };
        if handle as isize == -1 {
            return Err(std::io::Error::last_os_error());
        }
        Ok(unsafe { File::from_raw_handle(handle) })
    }
    pub fn replace(from: &Path, to: &Path) -> std::io::Result<()> {
        reject_reparse(to)?;
        unsafe { check(MoveFileExW(wide(from).as_ptr(), wide(to).as_ptr(), 1 | 8)) }
    }
}

#[cfg(windows)]
pub use credentials::{delete as credential_delete, get as credential_get, set as credential_set};
#[cfg(windows)]
mod credentials {
    use std::{ffi::c_void, ptr};
    #[repr(C)]
    struct Credential {
        flags: u32,
        kind: u32,
        target: *mut u16,
        comment: *mut u16,
        written: [u32; 2],
        size: u32,
        blob: *mut u8,
        persist: u32,
        attributes_count: u32,
        attributes: *mut c_void,
        alias: *mut u16,
        user: *mut u16,
    }
    #[link(name = "advapi32")]
    unsafe extern "system" {
        fn CredReadW(
            target: *const u16,
            kind: u32,
            flags: u32,
            credential: *mut *mut Credential,
        ) -> i32;
        fn CredWriteW(credential: *const Credential, flags: u32) -> i32;
        fn CredDeleteW(target: *const u16, kind: u32, flags: u32) -> i32;
        fn CredFree(buffer: *mut c_void);
    }
    pub fn get(service: &str, reference: &str) -> std::io::Result<String> {
        let mut credential = ptr::null_mut();
        unsafe {
            if CredReadW(
                super::credential_target(service, reference)?.as_ptr(),
                1,
                0,
                &mut credential,
            ) == 0
            {
                return Err(std::io::Error::last_os_error());
            }
            let c = &*credential;
            let bytes = if c.size == 0 {
                &[]
            } else {
                std::slice::from_raw_parts(c.blob, c.size as usize)
            };
            let result = String::from_utf8(bytes.to_vec())
                .map_err(|_| std::io::Error::other("Invalid Credential Manager value"));
            for offset in 0..c.size as usize {
                std::ptr::write_volatile(c.blob.add(offset), 0);
            }
            CredFree(credential.cast());
            result
        }
    }
    pub fn set(service: &str, reference: &str, value: &str) -> std::io::Result<()> {
        if value.len() > 2560 {
            return Err(std::io::Error::other(
                "Credential exceeds the Windows Credential Manager 2560-byte limit",
            ));
        }
        let mut name = super::credential_target(service, reference)?;
        let credential = Credential {
            flags: 0,
            kind: 1,
            target: name.as_mut_ptr(),
            comment: ptr::null_mut(),
            written: [0; 2],
            size: value.len() as u32,
            blob: value.as_ptr().cast_mut(),
            persist: 2,
            attributes_count: 0,
            attributes: ptr::null_mut(),
            alias: ptr::null_mut(),
            user: ptr::null_mut(),
        };
        if unsafe { CredWriteW(&credential, 0) } == 0 {
            Err(std::io::Error::last_os_error())
        } else {
            Ok(())
        }
    }
    pub fn delete(service: &str, reference: &str) -> std::io::Result<()> {
        if unsafe { CredDeleteW(super::credential_target(service, reference)?.as_ptr(), 1, 0) } != 0
        {
            return Ok(());
        }
        let error = std::io::Error::last_os_error();
        if error.raw_os_error() == Some(1168) {
            Ok(())
        } else {
            Err(error)
        }
    }
}

/// Exact UTF-16 vault identity; never allow Win32 NUL truncation collisions.
pub fn credential_target(service: &str, reference: &str) -> std::io::Result<Vec<u16>> {
    if service.contains('\0') || reference.contains('\0') {
        return Err(std::io::Error::other(
            "Credential reference must not contain NUL",
        ));
    }
    let target: Vec<u16> = format!("{service}:{reference}")
        .encode_utf16()
        .chain(Some(0))
        .collect();
    if target.len() > 32768 {
        return Err(std::io::Error::other(
            "Credential reference exceeds the Windows limit",
        ));
    }
    Ok(target)
}

/// Verify DOS and PE signatures before asking Windows to load the executable.
pub fn validate_windows_image(path: &Path) -> std::io::Result<()> {
    use std::io::{Read, Seek, SeekFrom};
    let mut file = File::open(path)?;
    let mut header = [0u8; 64];
    file.read_exact(&mut header)?;
    if &header[..2] != b"MZ" {
        return Err(std::io::Error::other(
            "Selected .exe is not a Windows executable",
        ));
    }
    let offset = u32::from_le_bytes(header[60..64].try_into().unwrap()) as u64;
    if offset < 64 {
        return Err(std::io::Error::other("Invalid Windows PE header offset"));
    }
    file.seek(SeekFrom::Start(offset))?;
    let mut signature = [0; 4];
    file.read_exact(&mut signature)?;
    if signature != *b"PE\0\0" {
        return Err(std::io::Error::other(
            "Selected .exe has no Windows PE header",
        ));
    }
    Ok(())
}
