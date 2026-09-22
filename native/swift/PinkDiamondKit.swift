// PinkDiamondKit — Swift companion for the iOS facet of Pink Diamond.
// Mirrors the ten-theme system so a saved theme restores identically on iOS.

import Foundation

public enum PinkTheme: String, CaseIterable, Codable {
    case neonRose = "neon-rose", porcelain, candlelight, coralDusk = "coral-dusk"
    case dark, obsidian, amethyst, emerald, sapphire, uviolet
}

public struct PinkAccount: Codable {
    public var email: String
    public var plan: String          // free | go | plus | pro | max
    public var apiBalance: Double    // 50% of every payment funds this
    public var theme: PinkTheme

    public static func funding(fromPriceCents price: Int64) -> Double {
        return Double(price) / 200.0 // 50% to the personal API key (spec §4)
    }
}