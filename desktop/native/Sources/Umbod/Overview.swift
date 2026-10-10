import SwiftUI
import Charts
import UmbodCore

struct Overview: View {
    @EnvironmentObject var model: AppModel
    @Binding var page: Page?
    var body: some View {
        ToolUsageView()
        if model.servers.isEmpty {
            Panel {
                Text("Connect your first tools").font(.headline)
                Text("Add a connector, enable its tools, then connect your AI app in Settings → MCP.").foregroundStyle(Brand.muted)
                Button("Add a connector") { page = .servers }.buttonStyle(BrandButtonStyle(primary: true))
            }
        }
    }
}

struct UsageRank: Identifiable {
    let id: String
    let name: String
    let connector: String
    let count: Int
}
struct UsagePoint: Identifiable {
    var id: Date { date }
    let date: Date
    let count: Int
}
struct ToolUsageView: View {
    @EnvironmentObject var model: AppModel
    @State private var selectedDate: Date?
    private var rows: [UsageRank] {
        model.toolUsage.map { name, values in
            let parts = name.split(separator: ".", maxSplits: 1).map(String.init)
            return UsageRank(id: name, name: parts.last ?? name, connector: connectorName(parts.first ?? name), count: (values["succeeded"] ?? 0) + (values["failed"] ?? 0))
        }.sorted { $0.count == $1.count ? $0.id < $1.id : $0.count > $1.count }
    }
    private var connectors: [UsageRank] {
        let grouped = Dictionary(grouping: rows) { $0.id.split(separator: ".", maxSplits: 1).first.map(String.init) ?? $0.id }
        return grouped.map { id, tools in
            UsageRank(id: id, name: connectorName(id), connector: "", count: tools.reduce(0) { $0 + $1.count })
        }.sorted { $0.count == $1.count ? $0.id < $1.id : $0.count > $1.count }
    }
    private var total: Int { rows.reduce(0) { $0 + $1.count } }
    private var points: [UsagePoint] {
        let today = Int(Date().timeIntervalSince1970) / 86400
        let days = model.dailyCalls.compactMap { key, value -> (Int, Int)? in
            guard let day = Int(key), day >= 0 else { return nil }
            return (day, value)
        }.sorted { $0.0 < $1.0 }
        let start = min(model.dailyTrackingStarted ?? today, days.first?.0 ?? today)
        var result = [UsagePoint(date: Date(timeIntervalSince1970: Double(start) * 86400), count: 0)]
        var cumulative = 0
        var previous = start
        for (day, calls) in days {
            if day > previous { result.append(UsagePoint(date: Date(timeIntervalSince1970: Double(day) * 86400), count: cumulative)) }
            cumulative += calls
            result.append(UsagePoint(date: Date(timeIntervalSince1970: Double(day + 1) * 86400), count: cumulative))
            previous = day + 1
        }
        if previous <= today { result.append(UsagePoint(date: Date(timeIntervalSince1970: Double(today + 1) * 86400), count: cumulative)) }
        return result
    }
    private var axisDates: [Date] {
        let first = Int(points.first!.date.timeIntervalSince1970) / 86400
        let last = Int(points.last!.date.timeIntervalSince1970) / 86400
        let step = max(1, (last - first + 4) / 5)
        var days = Array(stride(from: first, through: last, by: step))
        if days.last != last { days.append(last) }
        return days.map { Date(timeIntervalSince1970: Double($0) * 86400) }
    }
    private var selectedPoint: UsagePoint? {
        guard let selectedDate else { return nil }
        return points.min { abs($0.date.timeIntervalSince(selectedDate)) < abs($1.date.timeIntervalSince(selectedDate)) }
    }
    var body: some View {
        Panel {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("TOTAL TOOL CALLS").font(.system(size: 10, design: .monospaced)).tracking(1).foregroundStyle(Brand.muted)
                    Text(total.formatted()).font(.system(size: 44, weight: .semibold)).tracking(-1.5).monospacedDigit()
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 10) {
                    Text("Since tracking began").font(.caption).padding(8).background(Brand.accentSoft, in: Capsule())
                    Text("Daily totals · UTC").font(.caption).foregroundStyle(Brand.muted)
                }
            }
            HStack {
                Text("Cumulative calls").foregroundStyle(Brand.muted)
                Spacer()
                if let point = selectedPoint {
                    Text("\(dayLabel(point.date)) · \(point.count.formatted()) calls")
                }
            }.font(.caption)
            Chart {
                ForEach(points) { point in
                    AreaMark(x: .value("Date", point.date), y: .value("Calls", point.count))
                        .foregroundStyle(LinearGradient(colors: [Brand.accent.opacity(0.22), Brand.accent.opacity(0.025)], startPoint: .top, endPoint: .bottom))
                    LineMark(x: .value("Date", point.date), y: .value("Calls", point.count)).foregroundStyle(Brand.accent).lineStyle(StrokeStyle(lineWidth: 2.5))
                }
                if let point = selectedPoint {
                    RuleMark(x: .value("Date", point.date)).foregroundStyle(Brand.muted.opacity(0.3))
                    PointMark(x: .value("Date", point.date), y: .value("Calls", point.count)).foregroundStyle(Brand.accent)
                }
            }
            .chartYScale(domain: 0...max(5, points.last?.count ?? 0))
            .chartXScale(domain: points.first!.date...points.last!.date)
            .chartXAxis {
                AxisMarks(values: axisDates) { value in
                    AxisGridLine()
                    AxisValueLabel { if let date = value.as(Date.self) { Text(dayLabel(date)) } }
                }
            }
            .chartYAxis { AxisMarks(position: .leading) }
            .chartXSelection(value: $selectedDate)
            .chartOverlay { proxy in
                GeometryReader { geometry in
                    Color.clear.contentShape(Rectangle()).onContinuousHover { phase in
                        switch phase {
                        case .active(let location):
                            if let frame = proxy.plotFrame {
                                selectedDate = proxy.value(atX: location.x - geometry[frame].origin.x, as: Date.self)
                            }
                        case .ended: selectedDate = nil
                        }
                    }
                }
            }
            .environment(\.timeZone, TimeZone(secondsFromGMT: 0)!)
            .frame(height: 240)
            if total > (points.last?.count ?? 0) {
                Text("The chart includes calls recorded since daily tracking began. \((total - (points.last?.count ?? 0)).formatted()) earlier calls are included in the rankings below.").font(.caption).foregroundStyle(Brand.muted)
            } else if total == 0 {
                Text("Your chart will grow when an app uses a tool through Umbod.").font(.caption).foregroundStyle(Brand.muted)
            }
        }
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: 24) {
                connectorRanking.frame(minWidth: 260)
                toolRanking.frame(minWidth: 400)
            }
            VStack(alignment: .leading, spacing: 24) { connectorRanking; toolRanking }
        }
        Text("Local counts only. No arguments or results stored. Includes successful and failed dispatched calls.").font(.caption).foregroundStyle(Brand.muted)
            .task {
                while !Task.isCancelled {
                    if model.online && !model.busy { try? await model.refresh() }
                    do { try await Task.sleep(for: .seconds(5)) } catch { break }
                }
            }
    }
    private var connectorRanking: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Most-used connectors").font(.system(size: 20, weight: .semibold))
            Panel {
                HStack { Text("Connector"); Spacer(); Text("Calls").frame(width: 60, alignment: .trailing); Text("Share").frame(width: 50, alignment: .trailing) }.font(.caption).foregroundStyle(Brand.muted)
                if connectors.isEmpty { Text("Connector activity will appear here.").foregroundStyle(Brand.muted) }
                ForEach(connectors) { row in
                    Divider()
                    HStack { Text(row.name).frame(maxWidth: .infinity, alignment: .leading); Text(row.count.formatted()).monospacedDigit().frame(width: 60, alignment: .trailing); Text(total == 0 ? "0%" : "\(Int((Double(row.count) / Double(total) * 100).rounded()))%").foregroundStyle(Brand.muted).frame(width: 50, alignment: .trailing) }
                }
            }
        }.frame(maxWidth: .infinity)
    }
    private var toolRanking: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { Text("Most-used tools").font(.system(size: 20, weight: .semibold)); Spacer(); Text("Across connectors").font(.caption).foregroundStyle(Brand.muted) }
            Panel {
                HStack { Text("Tool").frame(maxWidth: .infinity, alignment: .leading); Text("Connector").frame(width: 100, alignment: .leading); Text("Calls").frame(width: 60, alignment: .trailing) }.font(.caption).foregroundStyle(Brand.muted)
                if rows.isEmpty { Text("Tools appear after their first call.").foregroundStyle(Brand.muted) }
                ForEach(rows) { row in
                    Divider()
                    HStack { Text(row.name).font(.system(size: 12, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading); Text(row.connector).font(.caption).foregroundStyle(Brand.muted).frame(width: 100, alignment: .leading); Text(row.count.formatted()).monospacedDigit().frame(width: 60, alignment: .trailing) }
                }
            }
        }.frame(maxWidth: .infinity)
    }
    private func dayLabel(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "MMM d"
        return formatter.string(from: date)
    }
    private func connectorName(_ id: String) -> String {
        model.servers.first { $0["id"] as? String == id }?["name"] as? String ?? "Removed connector (\(id.prefix(8)))"
    }
}
