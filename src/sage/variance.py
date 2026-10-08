"""
The variances tau of SAGE's compound Normal prior on each deviation eta (sec. 3.2), and the expectation
<1/tau> that enters the estimation of eta:
    jeffreys      improper Jeffreys prior P(tau) ~ 1/tau, parameter-free (the paper's choice for classification):
                  <1/tau> = 1/eta^2
    exponential   P(tau | gamma) = gamma exp(-gamma tau), i.e. a Laplace prior on eta: variational Gamma(a, b)
                  posterior, a by Newton steps and b in closed form (eq. 7); <1/tau> = 1/((a - 1) b)
"""
import torch

MIN_ETA2 = 1e-12      # an eta at exactly 0 has infinite <1/tau> under the Jeffreys prior: it stays at 0


def jeffreys_inv_tau(eta):
    return 1.0 / torch.clamp(eta * eta, min=MIN_ETA2)


def exponential_inv_tau(eta, gamma, a=None, steps=20):
    """(<1/tau>, a, b) under an Exponential(gamma) prior on tau, from eta (eq. 7). a: a warm start."""
    eta2 = torch.clamp(eta * eta, min=MIN_ETA2)
    a = torch.full_like(eta, 2.0) if a is None else a.clone()
    for _ in range(steps):
        b = (1 + torch.sqrt(1 + 8 * gamma * eta2 * a / (a - 1))) / (4 * gamma * a)
        psi1, psi2 = torch.special.polygamma(1, a), torch.special.polygamma(2, a)
        num = (0.5 - a) * psi1 + 0.5 * eta2 / b / (a - 1) ** 2 - gamma * b + 1
        den = (0.5 - a) * psi2 - psi1 - eta2 / b / (a - 1) ** 3
        a = torch.clamp(a - num / den, min=1.0 + 1e-6)        # -delta a = num / den; a > 1 keeps <1/tau> finite
    b = (1 + torch.sqrt(1 + 8 * gamma * eta2 * a / (a - 1))) / (4 * gamma * a)
    return 1.0 / ((a - 1) * b), a, b
