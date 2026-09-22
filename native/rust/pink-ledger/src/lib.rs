//! Pink Diamond credit + funding ledger.
//!
//! The 50% funding rule lives here as executable spec:
//! every payment splits half to the platform, half to the user's private
//! API key balance. Charges decrement credits; low/zero balance is flagged.

/// Outcome of applying a payment to an account.
#[derive(Debug, Clone, PartialEq)]
pub struct FundingResult {
    pub owner_share_cents: i64,
    pub api_key_funding_cents: i64,
    pub new_api_balance_cents: i64,
}

/// Split a payment: 50% funds the user's personal API key (spec §4).
pub fn fund_payment(payment_cents: i64, api_balance_cents: i64) -> FundingResult {
    let api_key_funding_cents = payment_cents_half(payment_cents);
    FundingResult {
        owner_share_cents: payment_cents - api_key_funding_cents,
        api_key_funding_cents,
        new_api_balance_cents: api_balance_cents + api_key_funding_cents,
    }
}

fn payment_cents_half(payment_cents: i64) -> i64 {
    payment_cents / 2 // integer-safe: odd cents round down to the owner share
}

/// Credit cost of an agent message (2 while Unfiltered Mode is on).
pub fn chat_cost_credits(unfiltered: bool) -> i64 {
    if unfiltered { 2 } else { 1 }
}

/// Low / zero balance flags — the spec requires a first-class notice.
pub fn low_balance_notice(credits_left: i64, api_balance_cents: i64, on_paid_plan: bool) -> Option<&'static str> {
    if credits_left <= 0 {
        Some("You are out of credits — generation pauses until you top up or upgrade.")
    } else if credits_left <= 25 {
        Some("Low credits: top up from Plans → Pay as you go.")
    } else if on_paid_plan && api_balance_cents <= 50 {
        Some("API key balance is low — half of every payment funds it; top up anytime.")
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn funding_splits_half() {
        let r = fund_payment_helper(1199, 0);
        assert_eq!(r.owner_share_cents, 1199 - 599);
        assert_eq!(r.api_key_funding_cents, 599); // $11.99 → $5.99 funds the key
        assert_eq!(r.new_api_balance_cents, 599);
    }

    fn fund_payment_helper(cents: i64, balance: i64) -> FundingResult { fund_payment(cents, balance) }

    #[test]
    fn chat_costs_double_unfiltered() {
        assert_eq!(chat_cost_credits(false), 1);
        assert_eq!(chat_cost_credits(true), 2);
    }

    #[test]
    fn notices_fire_in_order() {
        assert!(low_balance_notice(0, 5000, true).is_some());
        assert!(low_balance_notice(10, 5000, true).is_some());
        assert!(low_balance_notice(500, 20, true).is_some());
        assert!(low_balance_notice(500, 20, false).is_none());
        assert!(low_balance_notice(500, 5000, true).is_none());
    }
}