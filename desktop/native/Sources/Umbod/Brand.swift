import SwiftUI

// Ported from Umbod frontend's admin.css and AdminShell.svelte.
// Keep semantic colors and dimensions aligned with those sources.
enum Brand {
    static let ink = Color(hex: 0x14201c)
    static let muted = Color(hex: 0x5d6b64)
    static let canvas = Color.white
    static let soft = Color(hex: 0xf4f7f5)
    static let border = Color(hex: 0xdce4df)
    static let accent = Color(hex: 0x07634e)
    static let accentSoft = Color(hex: 0xe8f3ed)
    static let actionHover = Color(hex: 0x294638)
    static let disabled = Color(hex: 0xedf1ee)
    static let disabledText = Color(hex: 0x68776e)
    static let danger = Color(hex: 0xb42318)
    static let dangerSoft = Color(hex: 0xfff6f6)
}

private extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 255) / 255,
                  green: Double((hex >> 8) & 255) / 255, blue: Double(hex & 255) / 255, opacity: 1)
    }
}

// Exact path coordinates from frontend/static/umbod-logo.svg (viewBox 0 0 1254 1254).
struct UmbodMark: Shape {
    func path(in rect: CGRect) -> Path {
        let points: [CGPoint] = [
            .init(x: 582, y: 240), .init(x: 672, y: 240), .init(x: 672, y: 429),
            .init(x: 977, y: 720), .init(x: 977, y: 1012), .init(x: 887, y: 1012),
            .init(x: 887, y: 747), .init(x: 672, y: 543), .init(x: 672, y: 924),
            .init(x: 582, y: 924), .init(x: 582, y: 543), .init(x: 367, y: 747),
            .init(x: 367, y: 1012), .init(x: 277, y: 1012), .init(x: 277, y: 720),
            .init(x: 582, y: 429)
        ]
        var path = Path()
        path.addLines(points.map { CGPoint(x: rect.minX + $0.x / 1254 * rect.width, y: rect.minY + $0.y / 1254 * rect.height) })
        path.closeSubpath()
        return path
    }
}

struct BrandAppearance: ViewModifier {
    func body(content: Content) -> some View {
        content.font(.system(size: 14)).foregroundStyle(Brand.ink)
            .tint(Brand.accent).background(Brand.canvas)
            .buttonStyle(BrandButtonStyle()).textFieldStyle(BrandTextFieldStyle())
            .preferredColorScheme(.light)
    }
}

struct BrandButtonStyle: ButtonStyle {
    var primary = false
    @Environment(\.isEnabled) private var enabled
    @State private var hovered = false
    func makeBody(configuration: Configuration) -> some View {
        let destructive = configuration.role == .destructive
        configuration.label.font(.system(size: 14, weight: .semibold))
            .padding(.horizontal, 12).padding(.vertical, 8)
            .foregroundStyle(!enabled ? Brand.disabledText : primary ? .white : destructive ? Brand.danger : Brand.ink)
            .background(!enabled ? Brand.disabled : primary ? (hovered || configuration.isPressed ? Brand.actionHover : Brand.ink) : (hovered || configuration.isPressed ? Brand.soft : Brand.canvas), in: RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(primary && enabled ? Brand.ink : Brand.border))
            .contentShape(RoundedRectangle(cornerRadius: 8)).onHover { hovered = $0 }
    }
}

struct NavigationButtonStyle: ButtonStyle {
    let selected: Bool
    @State private var hovered = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.system(size: 14, weight: selected ? .semibold : .regular))
            .padding(.horizontal, 12).padding(.vertical, 10)
            .foregroundStyle(selected ? Brand.accent : Brand.muted)
            .background(selected || hovered || configuration.isPressed ? Brand.accentSoft : .clear, in: RoundedRectangle(cornerRadius: 8))
            .overlay(alignment: .leading) {
                if selected { Rectangle().fill(Brand.accent).frame(width: 2).padding(.vertical, 7) }
            }
            .contentShape(RoundedRectangle(cornerRadius: 8)).onHover { hovered = $0 }
    }
}

struct BrandTextFieldStyle: TextFieldStyle {
    @FocusState private var focused: Bool
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration.textFieldStyle(.plain).padding(.horizontal, 12).padding(.vertical, 8)
            .background(Brand.canvas, in: RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(focused ? Brand.accent : Brand.border, lineWidth: focused ? 2 : 1))
            .focused($focused)
    }
}
