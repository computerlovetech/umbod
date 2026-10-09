//! Fixture executable discovery is isolated from production configuration.
pub fn python() -> String {
    if cfg!(windows) {
        let output = std::process::Command::new("python")
            .args(["-c", "import sys; print(sys.executable)"])
            .output()
            .expect("Python fixture prerequisite");
        assert!(output.status.success());
        String::from_utf8(output.stdout).unwrap().trim().to_owned()
    } else {
        "/usr/bin/python3".into()
    }
}
