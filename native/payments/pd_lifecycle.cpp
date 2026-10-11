// Pink Diamond payment core (C++): subscription lifecycle.
//
// Stripe Billing performs the actual auto-renewal charge at the end of each
// period; this state machine decides what Pink Diamond does with the events
// it reports, so entitlement never drifts from what was actually paid:
//
//   NONE/PAST_DUE/CANCELED --invoice.paid--> ACTIVE          (renewal funds the balance)
//   ACTIVE --payment_failed--> PAST_DUE                      (access paused, Stripe retries)
//   ACTIVE --cancel_at_period_end--> CANCELING --resumed--> ACTIVE
//   any --deleted--> CANCELED
#include "pd_pay.h"

#include <array>

namespace {

constexpr int kStates = 5;
constexpr int kEvents = 6;  // index 0 unused

// kTable[state][event] = next state; -1 = unchanged.
constexpr std::array<std::array<int, kEvents>, kStates> kTable = {{
    //            -   PAID           FAILED            CANCEL_END         RESUMED        DELETED
    /* NONE */    {-1, PD_SUB_ACTIVE, -1,               -1,                -1,            PD_SUB_CANCELED},
    /* ACTIVE */  {-1, PD_SUB_ACTIVE, PD_SUB_PAST_DUE,  PD_SUB_CANCELING,  -1,            PD_SUB_CANCELED},
    /* PAST_DUE */{-1, PD_SUB_ACTIVE, -1,               PD_SUB_CANCELING,  -1,            PD_SUB_CANCELED},
    /* CANCELING*/{-1, PD_SUB_CANCELING, PD_SUB_PAST_DUE, -1,              PD_SUB_ACTIVE, PD_SUB_CANCELED},
    /* CANCELED */{-1, PD_SUB_ACTIVE, -1,               -1,                -1,            -1},
}};

bool valid_state(int s) { return s >= 0 && s < kStates; }

}  // namespace

extern "C" PD_PAY_API int pd_sub_transition(int state, int event) {
    if (!valid_state(state) || event <= 0 || event >= kEvents) return state;
    const int next = kTable[static_cast<std::size_t>(state)][static_cast<std::size_t>(event)];
    return next < 0 ? state : next;
}

extern "C" PD_PAY_API int pd_sub_entitled(int state, int64_t period_end, int64_t now) {
    // A canceling subscription keeps what it paid for until the period ends.
    if (state == PD_SUB_ACTIVE || state == PD_SUB_CANCELING) return period_end > now ? 1 : 0;
    return 0;
}
