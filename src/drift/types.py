"""A drift score: a size (0 = same meaning, 1 = unrelated) and, where the method can tell, a kind of change."""
from dataclasses import dataclass, field
from typing import Optional

EQUIVALENT, NARROWER, BROADER, SHIFTED, CONTRADICTED = 'equivalent', 'narrower', 'broader', 'shifted', 'contradicted'
# narrower: the rendering says more than the source (it implies the source, not the reverse)
# broader:  the rendering says less (the source implies it, not the reverse)
# shifted:  neither implies the other;  contradicted: either contradicts the other


@dataclass
class Drift:
    size: float
    kind: Optional[str] = None       # one of the kinds above, or None when the method only measures size
    method: str = ''
    details: dict = field(default_factory=dict)
