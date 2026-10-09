//! Process-wide credential isolation. Selected once before any gateway work.
use std::{path::PathBuf, sync::OnceLock};
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Profile {
    Release,
    Dev,
}
static PROFILE: OnceLock<Profile> = OnceLock::new();
impl Profile {
    pub fn parse(value: &str) -> anyhow::Result<Self> {
        match value.trim() {
            "release" => Ok(Self::Release),
            "dev" => Ok(Self::Dev),
            _ => anyhow::bail!("Unknown Umbod profile: {value}"),
        }
    }
    pub fn name(self) -> &'static str {
        match self {
            Self::Release => "release",
            Self::Dev => "dev",
        }
    }
    pub fn service(self) -> &'static str {
        match self {
            Self::Release => "app.umbod.desktop",
            Self::Dev => "app.umbod.desktop.dev",
        }
    }
    pub fn directory(self) -> anyhow::Result<PathBuf> {
        #[cfg(windows)]
        let root = PathBuf::from(
            std::env::var_os("LOCALAPPDATA")
                .ok_or_else(|| anyhow::anyhow!("LOCALAPPDATA is unavailable"))?,
        );
        #[cfg(not(windows))]
        let root = PathBuf::from(std::env::var("HOME")?).join("Library/Application Support");
        Ok(root.join(match self {
            Self::Release => "Umbod",
            Self::Dev => "Umbod Dev",
        }))
    }
}
pub fn initialize(profile: Profile) -> anyhow::Result<()> {
    PROFILE
        .set(profile)
        .map_err(|_| anyhow::anyhow!("Profile already selected"))
}
pub fn current() -> Profile {
    *PROFILE.get().unwrap_or(&Profile::Release)
}
