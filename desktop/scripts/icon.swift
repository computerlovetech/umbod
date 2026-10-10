import AppKit
import Foundation
let directory = CommandLine.arguments[1]
try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
for size in [16,32,128,256,512] {
    for scale in [1,2] {
        let pixels = size * scale
        let image = NSImage(size: NSSize(width: pixels, height: pixels))
        image.lockFocus()
        let context = NSGraphicsContext.current!.cgContext
        context.scaleBy(x: CGFloat(pixels)/1024, y: CGFloat(pixels)/1024)
        // Umbod's canonical black mark on white, matching its web app icon.
        context.setFillColor(NSColor.white.cgColor)
        context.addPath(CGPath(roundedRect: CGRect(x: 36, y: 36, width: 952, height: 952), cornerWidth: 220, cornerHeight: 220, transform: nil))
        context.fillPath()
        context.saveGState()
        context.translateBy(x: 0, y: 1024)
        context.scaleBy(x: 1024.0 / 1254, y: -1024.0 / 1254)
        let points: [CGPoint] = [
            CGPoint(x: 582, y: 240), CGPoint(x: 672, y: 240), CGPoint(x: 672, y: 429),
            CGPoint(x: 977, y: 720), CGPoint(x: 977, y: 1012), CGPoint(x: 887, y: 1012),
            CGPoint(x: 887, y: 747), CGPoint(x: 672, y: 543), CGPoint(x: 672, y: 924),
            CGPoint(x: 582, y: 924), CGPoint(x: 582, y: 543), CGPoint(x: 367, y: 747),
            CGPoint(x: 367, y: 1012), CGPoint(x: 277, y: 1012), CGPoint(x: 277, y: 720),
            CGPoint(x: 582, y: 429)
        ]
        context.addLines(between: points)
        context.closePath()
        context.setFillColor(NSColor.black.cgColor)
        context.fillPath()
        context.restoreGState()
        if CommandLine.arguments.dropFirst(2).first == "dev" {
            context.setFillColor(NSColor(calibratedRed: 0.04, green: 0.38, blue: 0.30, alpha: 1).cgColor)
            context.fill(CGRect(x: 160, y: 80, width: 704, height: 200))
            let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .center
            ("DEV" as NSString).draw(in: NSRect(x: 160, y: 80, width: 704, height: 190), withAttributes: [.font: NSFont.systemFont(ofSize: 150, weight: .bold), .foregroundColor: NSColor.white, .paragraphStyle: paragraph])
        }
        image.unlockFocus()
        let representation = NSBitmapImageRep(data: image.tiffRepresentation!)!
        let suffix = scale == 2 ? "@2x" : ""
        try representation.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "\(directory)/icon_\(size)x\(size)\(suffix).png"))
    }
}
