// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "Umbod", platforms: [.macOS(.v14)], products: [.executable(name: "Umbod", targets: ["Umbod"])], targets: [.target(name: "UmbodCore"), .executableTarget(name: "Umbod", dependencies: ["UmbodCore"]), .executableTarget(name: "UmbodTests", dependencies: ["UmbodCore"], path: "Tests/UmbodTests")])
