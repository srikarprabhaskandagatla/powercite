from typing import Literal, Optional
from pydantic import BaseModel


class DemandCharge(BaseModel):
    rate_class: str
    component: str
    usd_per_unit: float
    unit: Literal["kW", "kVA"]
    optional: bool
    quote: str


class Incentive(BaseModel):
    program: str
    customer_type: Literal["business", "residential", "unknown"]
    usd_per_kw: float
    applies_to_batteries: bool
    quote: str


class PageFacts(BaseModel):
    utility: Optional[str]
    effective_date: Optional[str]
    effective_quote: Optional[str]
    demand_charges: list[DemandCharge]
    incentives: list[Incentive]
