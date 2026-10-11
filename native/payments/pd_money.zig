//! Pink Diamond payment core (Zig): the money arithmetic.
//!
//! All amounts are integer cents. Nothing here ever sees a card; it only
//! divides up amounts Stripe has already settled.
//!
//!   zig test pd_money.zig

const std = @import("std");

/// $1 = 100 Pink Credits, so one credit is one cent of model spend.
pub const credits_per_dollar: i64 = 100;
/// Yearly billing: twelve months at 20% off.
pub const yearly_percent: i64 = 80;
/// Pay-as-you-go custom amount bounds.
pub const topup_min_cents: i64 = 500;
pub const topup_max_cents: i64 = 100_000;

/// Half of a subscription payment funds the customer's model balance; an odd
/// cent rounds in the customer's favour.
pub fn splitCustomer(paid_cents: i64) i64 {
    if (paid_cents <= 0) return 0;
    return paid_cents - @divTrunc(paid_cents, 2);
}

pub fn splitPlatform(paid_cents: i64) i64 {
    if (paid_cents <= 0) return 0;
    return @divTrunc(paid_cents, 2);
}

pub fn centsToCredits(cents: i64) i64 {
    if (cents <= 0) return 0;
    return @divTrunc(cents * credits_per_dollar, 100);
}

/// interval: 0 = month, 1 = year.
pub fn planPriceCents(monthly_cents: i64, interval: c_int) i64 {
    if (monthly_cents <= 0) return 0;
    if (interval == 0) return monthly_cents;
    // round half up: (12 * m * 80 + 50) / 100
    return @divTrunc(12 * monthly_cents * yearly_percent + 50, 100);
}

pub fn topupValid(cents: i64) bool {
    return cents >= topup_min_cents and cents <= topup_max_cents;
}

// ------------------------------------------------------------- C ABI ---

export fn pd_split_customer_cents(paid_cents: i64) i64 {
    return splitCustomer(paid_cents);
}
export fn pd_split_platform_cents(paid_cents: i64) i64 {
    return splitPlatform(paid_cents);
}
export fn pd_cents_to_credits(cents: i64) i64 {
    return centsToCredits(cents);
}
export fn pd_plan_price_cents(monthly_cents: i64, interval: c_int) i64 {
    return planPriceCents(monthly_cents, interval);
}
export fn pd_topup_valid(cents: i64) c_int {
    return @intFromBool(topupValid(cents));
}

// ------------------------------------------------------------- tests ---

test "split always adds back up to the payment" {
    const amounts = [_]i64{ 1, 2, 1199, 2299, 3399, 12199, 99_999 };
    for (amounts) |a| {
        try std.testing.expectEqual(a, splitCustomer(a) + splitPlatform(a));
    }
    try std.testing.expectEqual(@as(i64, 1150), splitCustomer(2299)); // Plus: $11.50 funds the user
    try std.testing.expectEqual(@as(i64, 0), splitCustomer(-5));
}

test "one dollar is one hundred pink credits" {
    try std.testing.expectEqual(@as(i64, 100), centsToCredits(100));
    try std.testing.expectEqual(@as(i64, 50_000), centsToCredits(50_000));
    try std.testing.expectEqual(@as(i64, 1150), centsToCredits(1150));
}

test "yearly is twelve months at 20% off" {
    try std.testing.expectEqual(@as(i64, 2299), planPriceCents(2299, 0));
    try std.testing.expectEqual(@as(i64, 22070), planPriceCents(2299, 1)); // 220.704 -> 220.70
    try std.testing.expectEqual(@as(i64, 9600), planPriceCents(1000, 1)); // uncensored add-on yearly
}

test "custom top-up bounds" {
    try std.testing.expect(!topupValid(499));
    try std.testing.expect(topupValid(500));
    try std.testing.expect(topupValid(50_000));
    try std.testing.expect(!topupValid(100_001));
}
