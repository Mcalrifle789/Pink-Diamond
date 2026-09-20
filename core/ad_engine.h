// Pink Diamond ad engine — public interface.
#pragma once

#include <cstddef>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#if defined(_WIN32)
  #define PD_API __declspec(dllexport)
#else
  #define PD_API __attribute__((visibility("default")))
#endif

namespace pd {

struct AdSlot {
    std::string placement;   // rail_left | rail_right | bottom | popup
    std::string box;         // black | grey
    int price_usd;           // 400 | 400 | 350 | 0
};

struct PopupState {
    int shown = 0;
    long last_shown = 0;
    long suppressed_until = 0;
};

inline constexpr int kMaxPopupsPerSession = 2;
inline constexpr long kMinPopupGapSeconds = 90;
inline constexpr long kDismissSuppressionSeconds = 12 * 3600;

class AdEngine {
  public:
    AdEngine();
    explicit AdEngine(std::vector<AdSlot> inventory);

    const AdSlot& slot(const std::string& placement) const;

    // Black boxes: appear, stay, rotate to the next creative in sequence.
    long next_creative(const std::string& placement);

    // Grey boxes (pop-ups): cap + gap + suppression policy.
    bool popup_allowed(long now_epoch_seconds);
    void record_popup_shown(long now_epoch_seconds);
    void dismiss_popup(long now_epoch_seconds);

  private:
    PopupState& popup_state() { return popup_; }
    std::vector<AdSlot> inventory_;
    std::vector<long> cursors_;
    PopupState popup_;
    long long session_start_;
};

}  // namespace pd
