// Pink Diamond ad engine.
//
// Implements the placement rules from the monetization spec:
//   - black boxes: creatives appear, stay, and rotate to the next in sequence
//   - grey boxes (pop-ups): dismissible, max 2 per session, 90s minimum gap,
//     12h suppression after a dismissal
//
// Built as a shared library and consumed by backend/ad_engine.py; also builds
// a small CLI smoke test.

#include "ad_engine.h"

#include <algorithm>
#include <chrono>

namespace pd {

namespace {
std::vector<AdSlot> default_inventory() {
    return {
        {"rail_left",  "black", 400},
        {"rail_right", "black", 400},
        {"bottom",     "black", 350},
        {"popup",      "grey",  0},
    };
}
}  // namespace

AdEngine::AdEngine() : AdEngine(default_inventory()) {}

AdEngine::AdEngine(std::vector<AdSlot> inventory)
    : inventory_(std::move(inventory)),
      session_start_(std::chrono::steady_clock::now().time_since_epoch().count()) {
    cursors_.reserve(inventory_.size());
    for (const auto& slot : inventory_) cursors_.push_back(0);
}

const AdSlot& AdEngine::slot(const std::string& placement) const {
    for (const auto& slot : inventory_) {
        if (slot.placement == placement) return slot;
    }
    throw std::out_of_range("unknown placement: " + placement);
}

// Black boxes rotate in sequence: each call advances the cursor and returns the
// creative index now on display. The box stays until the next rotation tick.
long AdEngine::next_creative(const std::string& placement) {
    const AdSlot& s = slot(placement);
    if (s.box != "black") throw std::invalid_argument("rotation applies to black boxes only");
    const auto it = std::find_if(inventory_.begin(), inventory_.end(),
        [&](const AdSlot& x) { return x.placement == placement; });
    const auto idx = static_cast<std::size_t>(it - inventory_.begin());
    long& cursor = cursors_[idx];
    const long current = cursor;
    cursor += 1;  // wrap handled by the caller's creative list length
    return current;
}

bool AdEngine::popup_allowed(long now_epoch_seconds) {
    auto& state = popup_state();
    if (now_epoch_seconds < state.suppressed_until) return false;
    if (state.shown >= kMaxPopupsPerSession) return false;
    if (state.shown > 0 &&
        now_epoch_seconds - state.last_shown < kMinPopupGapSeconds) return false;
    return true;
}

void AdEngine::record_popup_shown(long now_epoch_seconds) {
    auto& state = popup_state();
    state.shown += 1;
    state.last_shown = now_epoch_seconds;
}

// The grey box's × : dismiss and suppress further pop-ups for 12 hours.
void AdEngine::dismiss_popup(long now_epoch_seconds) {
    auto& state = popup_state();
    state.suppressed_until = now_epoch_seconds + kDismissSuppressionSeconds;
}

}  // namespace pd

// ----------------------------------------------------------- C ABI for ctypes

extern "C" {

PD_API void* pd_engine_new() { return new pd::AdEngine(); }

PD_API void pd_engine_free(void* engine) { delete static_cast<pd::AdEngine*>(engine); }

PD_API long pd_next_creative(void* engine, const char* placement) {
    return static_cast<pd::AdEngine*>(engine)->next_creative(placement);
}

PD_API int pd_popup_allowed(void* engine, long now) {
    return static_cast<pd::AdEngine*>(engine)->popup_allowed(now) ? 1 : 0;
}

PD_API void pd_popup_shown(void* engine, long now) {
    static_cast<pd::AdEngine*>(engine)->record_popup_shown(now);
}

PD_API void pd_popup_dismiss(void* engine, long now) {
    static_cast<pd::AdEngine*>(engine)->dismiss_popup(now);
}

PD_API int pd_slot_price(void* engine, const char* placement) {
    return static_cast<pd::AdEngine*>(engine)->slot(placement).price_usd;
}

}  // extern "C"

#ifdef PD_AD_ENGINE_CLI
int main() {
    pd::AdEngine engine;
    std::cout << "rail_left price: $" << engine.slot("rail_left").price_usd << "\n";
    for (int i = 0; i < 3; ++i) std::cout << "rail_left creative #" << engine.next_creative("rail_left") << "\n";
    long now = 1'700'000'000;
    for (int i = 0; i < 3; ++i) {
        if (engine.popup_allowed(now)) { engine.record_popup_shown(now); std::cout << "popup shown\n"; }
        now += 90;  // respects the 90s gap, then hits the 2-per-session cap
    }
    engine.dismiss_popup(now);
    std::cout << "after dismiss, allowed: " << engine.popup_allowed(now + 3600) << "\n";
    std::cout << "12h later, allowed: " << engine.popup_allowed(now + 12 * 3600 + 1) << "\n";
    return 0;
}
#endif
