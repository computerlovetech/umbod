import SwiftUI

enum MCPClientGuide: String, CaseIterable, Identifiable {
    case claude = "Claude Desktop", chatGPT = "ChatGPT", gemini = "Gemini CLI", cursor = "Cursor"
    var id: String { rawValue }
    var symbol: String { switch self { case .claude: "text.bubble"; case .chatGPT: "bubble.left.and.bubble.right"; case .gemini: "sparkles"; case .cursor: "cursorarrow" } }
    var summary: String { self == .chatGPT ? "Requires a remotely accessible MCP endpoint." : "Use your enabled Umbod tools in \(rawValue)." }
    var instructions: String {
        switch self {
        case .claude: "1. Open Claude Desktop → Settings → Developer → Edit Config.\n\n2. Copy the configuration below and merge its server entry into mcpServers in claude_desktop_config.json. Keep your existing entries.\n\n3. Save the file and restart Claude Desktop. Start Umbod once; its gateway continues running after you quit the app."
        case .cursor: "1. Open ~/.cursor/mcp.json for your user configuration, or .cursor/mcp.json in your project.\n\n2. Copy the configuration below and merge its server entry into mcpServers. Keep your existing entries.\n\n3. Enable Umbod in Cursor's MCP settings. Start Umbod once; its gateway continues running after you quit the app."
        case .gemini: "1. Open ~/.gemini/settings.json.\n\n2. Copy the configuration below and merge its server entry into mcpServers. Keep your other settings.\n\n3. Restart Gemini CLI and use /mcp to check the connection. Start Umbod once; its gateway continues running after you quit the app. This guide is for Gemini CLI, not the Gemini web app."
        case .chatGPT: "ChatGPT's MCP connections run remotely. This build of Umbod listens only on your Mac, so its local address cannot be used directly in ChatGPT.\n\nA hosted Umbod endpoint is needed for this connection. Local client setup is available for Claude Desktop, Cursor, Gemini CLI, and other clients that support stdio."
        }
    }
    var documentation: URL {
        let address = switch self {
        case .claude: "https://modelcontextprotocol.io/docs/develop/connect-local-servers"
        case .cursor: "https://cursor.com/docs/context/mcp"
        case .gemini: "https://geminicli.com/docs/tools/mcp-server/"
        case .chatGPT: "https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt"
        }
        return URL(string: address)!
    }
}

struct MCPGuideSheet: View {
    @Environment(\.dismiss) private var dismiss
    let client: MCPClientGuide
    let configuration: String
    let copy: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text(client == .chatGPT ? "ChatGPT connection" : "Set up \(client.rawValue)").font(.system(size: 24, weight: .semibold))
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(client.instructions).foregroundStyle(Brand.muted).frame(maxWidth: .infinity, alignment: .leading)
                    if client != .chatGPT {
                        Text(configuration).font(.system(size: 12, design: .monospaced)).textSelection(.enabled)
                            .padding(16).frame(maxWidth: .infinity, alignment: .leading).background(Brand.soft, in: RoundedRectangle(cornerRadius: 8))
                        Button("Copy configuration") { copy() }.buttonStyle(BrandButtonStyle(primary: true))
                    }
                    Link("Official setup documentation", destination: client.documentation)
                }
            }
            HStack { Spacer(); Button("Done") { dismiss() } }
        }.padding(28).frame(width: 620, height: client == .chatGPT ? 370 : 620).modifier(BrandAppearance())
    }
}
