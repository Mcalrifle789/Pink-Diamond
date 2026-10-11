//! Pink Diamond model-switching entitlement.
//!
//! The update spec as executable rules:
//! - an account with an active subscription may switch between every model,
//!   across every agent (chat, image, video, audio);
//! - an account without one never reaches a model served by OpenRouter and is
//!   pinned to each agent's house default.
//!
//! `backend/main.py::_resolve_model` and the picker in `app.js` implement the
//! same table; the tests below are the reference behaviour.

/// Where a model is served from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Provider {
    /// Built into Pink Diamond — no OpenRouter call, available on Free.
    House,
    /// Routed through OpenRouter — subscribers only.
    OpenRouter,
    /// Image / video / audio studio partners — subscribers only.
    Studio,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Agent {
    Chat,
    Image,
    Video,
    Audio,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Plan {
    Free,
    Go,
    Plus,
    Pro,
    Max,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Model {
    pub id: &'static str,
    pub agent: Agent,
    pub provider: Provider,
}

/// Account state the decision depends on.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Account {
    pub plan: Plan,
    /// The plan subscription is paid up (not lapsed).
    pub subscription_active: bool,
}

impl Account {
    pub fn subscribed(&self) -> bool {
        self.plan != Plan::Free && self.subscription_active
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Denied {
    SubscriptionRequired,
    WrongAgent,
}

/// The default each agent falls back to; always a house model.
pub fn house_default(agent: Agent) -> Model {
    let id = match agent {
        Agent::Chat => "pink-diamond/lite",
        Agent::Image => "pink-diamond/open-image",
        Agent::Video => "pink-diamond/open-video",
        Agent::Audio => "pink-diamond/open-audio",
    };
    Model { id, agent, provider: Provider::House }
}

/// May `account` select `model` for `agent`?
pub fn can_use(account: &Account, agent: Agent, model: &Model) -> Result<(), Denied> {
    if model.agent != agent {
        return Err(Denied::WrongAgent);
    }
    if model.provider == Provider::House {
        return Ok(());
    }
    if account.subscribed() {
        Ok(())
    } else {
        Err(Denied::SubscriptionRequired)
    }
}

/// The model a request actually runs on: the requested one when allowed,
/// otherwise the agent's house default.
pub fn resolve(account: &Account, agent: Agent, requested: Option<&Model>) -> Model {
    match requested {
        Some(m) if can_use(account, agent, m).is_ok() => *m,
        _ => house_default(agent),
    }
}

/// Whether the chat agent may call OpenRouter at all for this account.
pub fn openrouter_allowed(account: &Account) -> bool {
    account.subscribed()
}

#[cfg(test)]
mod tests {
    use super::*;

    const GPT5: Model = Model { id: "openai/gpt-5.5", agent: Agent::Chat, provider: Provider::OpenRouter };
    const KLING: Model = Model { id: "kling-3.0", agent: Agent::Video, provider: Provider::Studio };

    fn free() -> Account { Account { plan: Plan::Free, subscription_active: false } }
    fn plus() -> Account { Account { plan: Plan::Plus, subscription_active: true } }

    #[test]
    fn free_accounts_never_reach_openrouter() {
        assert!(!openrouter_allowed(&free()));
        assert_eq!(can_use(&free(), Agent::Chat, &GPT5), Err(Denied::SubscriptionRequired));
        assert_eq!(resolve(&free(), Agent::Chat, Some(&GPT5)).provider, Provider::House);
    }

    #[test]
    fn free_accounts_keep_house_models() {
        let lite = house_default(Agent::Chat);
        assert_eq!(can_use(&free(), Agent::Chat, &lite), Ok(()));
    }

    #[test]
    fn subscribers_switch_across_all_agents() {
        assert_eq!(resolve(&plus(), Agent::Chat, Some(&GPT5)), GPT5);
        assert_eq!(resolve(&plus(), Agent::Video, Some(&KLING)), KLING);
        for plan in [Plan::Go, Plan::Plus, Plan::Pro, Plan::Max] {
            assert!(openrouter_allowed(&Account { plan, subscription_active: true }));
        }
    }

    #[test]
    fn lapsed_subscription_loses_switching() {
        let lapsed = Account { plan: Plan::Pro, subscription_active: false };
        assert_eq!(can_use(&lapsed, Agent::Chat, &GPT5), Err(Denied::SubscriptionRequired));
    }

    #[test]
    fn models_stay_in_their_agent() {
        assert_eq!(can_use(&plus(), Agent::Chat, &KLING), Err(Denied::WrongAgent));
        assert_eq!(resolve(&plus(), Agent::Chat, Some(&KLING)), house_default(Agent::Chat));
    }

    #[test]
    fn no_request_means_house_default() {
        assert_eq!(resolve(&plus(), Agent::Audio, None), house_default(Agent::Audio));
    }
}
