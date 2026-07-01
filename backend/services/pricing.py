"""
Pricing Engine - Calculates fair prices for link placements based on existing data.
Uses DR bracket + traffic to determine fair market value.
Auto-negotiation: only counters when asking price exceeds fair value.
"""

import statistics
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..models import Domain, LinkPrice


# DR brackets and their $/1K traffic rates (will be computed from data)
DR_BRACKETS = [(0, 25), (25, 40), (40, 55), (55, 70), (70, 100)]

# Minimum price floor - any permanent do-follow link has baseline value
PRICE_FLOOR = 50.0

# Tolerance: accept if asking price is within this % above fair value
ACCEPT_THRESHOLD_PCT = 20


def get_pricing_data(db: Session, link_type: str = "Guest Post") -> list[dict]:
    """Pull all domains with prices and traffic for a given link type."""
    rows = db.execute(
        text("""
        SELECT d.domain, d.domain_rating, d.organic_traffic,
               lp.price, lp.is_permanent, lp.duration_months
        FROM domains d
        JOIN link_prices lp ON lp.domain_id = d.id
        WHERE lp.price > 0
          AND d.organic_traffic > 0
          AND d.domain_rating > 0
          AND lp.link_type = :link_type
          AND lp.deleted_at IS NULL
          AND d.deleted_at IS NULL
        ORDER BY d.organic_traffic DESC
        """),
        {"link_type": link_type},
    ).fetchall()

    return [
        {
            "domain": r[0],
            "dr": r[1],
            "traffic": r[2],
            "price": r[3],
            "is_permanent": r[4],
            "duration_months": r[5],
            "cost_per_1k": (r[3] / r[2]) * 1000 if r[2] > 0 else 0,
        }
        for r in rows
    ]


def compute_bracket_rates(data: list[dict]) -> dict:
    """Compute median $/1K traffic for each DR bracket."""
    rates = {}
    for lo, hi in DR_BRACKETS:
        subset = [d["cost_per_1k"] for d in data if lo <= d["dr"] < hi]
        if subset:
            rates[(lo, hi)] = statistics.median(subset)

    # Overall median as fallback
    all_rates = [d["cost_per_1k"] for d in data]
    if all_rates:
        rates["overall"] = statistics.median(all_rates)
    else:
        rates["overall"] = 3.0  # sensible default

    return rates


def get_bracket_rate(rates: dict, dr: int) -> float:
    """Get the $/1K rate for a given DR value."""
    dr = int(dr)
    for lo, hi in DR_BRACKETS:
        if lo <= dr < hi and (lo, hi) in rates:
            return rates[(lo, hi)]
    return rates.get("overall", 3.0)


def calculate_fair_price(
    db: Session,
    domain_rating: int,
    organic_traffic: int,
    link_type: str = "Guest Post",
    exclude_domain: str | None = None,
) -> dict:
    """
    Calculate fair price for a link placement.
    Uses the lower of bracket rate and overall rate to avoid overpaying
    in brackets skewed by tiny overpriced sites.
    Excludes the target domain itself from the dataset to avoid circular pricing.
    """
    domain_rating = int(domain_rating)
    organic_traffic = int(organic_traffic)

    data = get_pricing_data(db, link_type)

    # Exclude the domain being evaluated (avoid circular pricing)
    if exclude_domain:
        data = [d for d in data if d["domain"] != exclude_domain]

    rates = compute_bracket_rates(data)

    bracket_rate = get_bracket_rate(rates, domain_rating)
    overall_rate = rates.get("overall", 3.0)

    # Use the LOWER of bracket rate and overall rate
    # This prevents overpaying in brackets skewed by tiny sites with insane $/1K
    effective_rate = min(bracket_rate, overall_rate)

    # Fair price = max(floor, traffic/1000 * effective_rate)
    raw_price = (organic_traffic / 1000) * effective_rate
    fair_price = max(PRICE_FLOOR, raw_price)

    # Determine which bracket
    bracket = None
    for lo, hi in DR_BRACKETS:
        if lo <= domain_rating < hi:
            bracket = f"DR {lo}-{hi}"
            break

    # Confidence based on how many data points in bracket
    bracket_count = sum(1 for d in data if any(
        lo <= d["dr"] < hi for lo, hi in DR_BRACKETS
        if lo <= domain_rating < hi
    ))

    return {
        "fair_price": round(fair_price, 2),
        "bracket_rate": round(bracket_rate, 2),
        "effective_rate": round(effective_rate, 2),
        "bracket": bracket,
        "bracket_data_points": bracket_count,
        "overall_rate": round(overall_rate, 2),
        "price_floor": PRICE_FLOOR,
        "confidence": "high" if bracket_count >= 5 else "medium" if bracket_count >= 3 else "low",
    }


def evaluate_asking_price(
    db: Session,
    domain_rating: int,
    organic_traffic: int,
    asking_price: float,
    link_type: str = "Guest Post",
    exclude_domain: str | None = None,
) -> dict:
    """
    Evaluate whether an asking price is fair.
    Returns verdict + suggested counter-offer if overpriced.
    """
    calc = calculate_fair_price(db, domain_rating, organic_traffic, link_type, exclude_domain)
    fair = calc["fair_price"]

    max_acceptable = fair * (1 + ACCEPT_THRESHOLD_PCT / 100)

    if asking_price <= fair:
        verdict = "good_deal"
        action = "accept"
        counter_offer = None
    elif asking_price <= max_acceptable:
        verdict = "acceptable"
        action = "accept"
        counter_offer = None
    else:
        verdict = "overpriced"
        action = "counter"
        # Counter strategy:
        # - Start with 50% of asking price (realistic negotiation floor)
        # - But if even 50% is more than 2x fair value, use fair + 20% instead
        #   (no point overpaying just to be polite)
        half_asking = asking_price * 0.5
        fair_plus = max_acceptable  # fair + 20%
        
        if half_asking <= fair_plus * 2:
            # 50% of asking is reasonable, use the higher of fair and 50%
            counter_offer = max(half_asking, fair_plus)
        else:
            # Even 50% is way too much, counter at fair + 20%
            counter_offer = fair_plus
        
        counter_offer = round(counter_offer / 5) * 5
        if counter_offer < PRICE_FLOOR:
            counter_offer = PRICE_FLOOR

    return {
        **calc,
        "asking_price": asking_price,
        "max_acceptable": round(max_acceptable, 2),
        "verdict": verdict,
        "action": action,
        "counter_offer": counter_offer,
    }


def evaluate_domain_prices(db: Session, domain_id: str) -> list[dict]:
    """Evaluate all link prices for a domain. Returns list of evaluations."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        return []

    prices = db.query(LinkPrice).filter(
        LinkPrice.domain_id == domain_id,
        LinkPrice.deleted_at.is_(None),
        LinkPrice.price > 0,
    ).all()

    results = []
    for lp in prices:
        eval_result = evaluate_asking_price(
            db,
            domain.domain_rating or 0,
            domain.organic_traffic or 0,
            lp.price,
            lp.link_type,
        )
        eval_result["link_price_id"] = lp.id
        eval_result["link_type"] = lp.link_type
        eval_result["domain"] = domain.domain
        results.append(eval_result)

    return results
