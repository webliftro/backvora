"""
Add Ross (EmpirEscort network) domains to BackVora with Ahrefs metrics.

Contact: Ross at EmpirEscort
Email: collaborations@trovagnocca.com
Telegram: @Ross8484
"""

import asyncio
import sys
from datetime import datetime
from sqlalchemy.orm import Session

# Add backend to path
sys.path.insert(0, '/home/slither/code/backvora')

from backend.database import SessionLocal
from backend.models import Domain, Contact, LinkPrice, DomainStatus
from backend.services.ahrefs import AhrefsService


# Ross's EmpirEscort network domains with pricing
DOMAINS = [
    {
        "domain": "empirescort.com",
        "languages": "EN/ES/PT",
        "region": "International",
        "claimed_traffic": 4_300_000,
        "blog_domain": "blog.empirescort.com",
        "price_1_link": 175,
        "price_2_links": 225,
        "notes": "International escort directory, blog at blog.empirescort.com"
    },
    {
        "domain": "trovagnocca.com",
        "languages": "IT",
        "region": "Italy",
        "claimed_traffic": 3_500_000,
        "blog_domain": None,
        "price_1_link": 200,
        "price_2_links": 250,
        "notes": "Italian escort directory, content must be in Italian"
    },
    {
        "domain": "itaincontri.com",
        "languages": "IT",
        "region": "Italy",
        "claimed_traffic": 2_000_000,
        "blog_domain": None,
        "price_1_link": 125,
        "price_2_links": 175,
        "notes": "Italian encounters/dating site, content must be in Italian"
    },
]


async def main():
    """Fetch metrics and add domains to database."""
    db: Session = SessionLocal()
    ahrefs = AhrefsService()
    
    results = []
    
    print(f"Processing {len(DOMAINS)} domains from Ross @ EmpirEscort network")
    print("=" * 80)
    print(f"Contact: collaborations@trovagnocca.com | Telegram: @Ross8484")
    print("=" * 80)
    
    for i, domain_info in enumerate(DOMAINS, 1):
        domain = domain_info["domain"]
        print(f"\n[{i}/{len(DOMAINS)}] {domain}")
        print(f"  Region: {domain_info['region']} | Languages: {domain_info['languages']}")
        print(f"  Claimed traffic: {domain_info['claimed_traffic']:,} users/month")
        print(f"  Pricing: 1 link = ${domain_info['price_1_link']}, 2 links = ${domain_info['price_2_links']}")
        
        # Check if domain already exists
        existing = db.query(Domain).filter(Domain.domain == domain).first()
        if existing:
            print(f"  ⚠️  Domain already exists (ID: {existing.id})")
            # Update if no metrics
            if not existing.domain_rating:
                print(f"  → Fetching metrics for existing domain...")
                try:
                    metrics = await ahrefs.get_domain_metrics(domain)
                    existing.domain_rating = metrics.get("domain_rating")
                    existing.organic_traffic = metrics.get("organic_traffic")
                    existing.referring_domains = metrics.get("referring_domains")
                    existing.backlinks_count = metrics.get("backlinks_count")
                    existing.status = DomainStatus.ANALYZED
                    existing.last_analyzed_at = datetime.utcnow()
                    db.commit()
                    
                    results.append({
                        **domain_info,
                        "dr": metrics.get("domain_rating"),
                        "actual_traffic": metrics.get("organic_traffic"),
                        "refdomains": metrics.get("referring_domains"),
                        "backlinks": metrics.get("backlinks_count"),
                        "status": "updated_existing"
                    })
                    print(f"  ✓ Updated: DR={metrics.get('domain_rating')}, Traffic={metrics.get('organic_traffic'):,}")
                except Exception as e:
                    print(f"  ✗ Error fetching metrics: {e}")
                    results.append({
                        **domain_info,
                        "dr": existing.domain_rating,
                        "actual_traffic": existing.organic_traffic,
                        "refdomains": existing.referring_domains,
                        "backlinks": existing.backlinks_count,
                        "status": "existing_no_update",
                        "error": str(e)
                    })
            else:
                results.append({
                    **domain_info,
                    "dr": existing.domain_rating,
                    "actual_traffic": existing.organic_traffic,
                    "refdomains": existing.referring_domains,
                    "backlinks": existing.backlinks_count,
                    "status": "existing"
                })
            
            await asyncio.sleep(2)
            continue
        
        # Fetch Ahrefs metrics
        try:
            print(f"  → Fetching Ahrefs metrics...")
            metrics = await ahrefs.get_domain_metrics(domain)
            
            dr = metrics.get("domain_rating")
            traffic = metrics.get("organic_traffic")
            refdomains = metrics.get("referring_domains")
            backlinks = metrics.get("backlinks_count")
            
            print(f"  ✓ Ahrefs: DR={dr}, Traffic={traffic:,}, RefDomains={refdomains:,}, Backlinks={backlinks:,}")
            
            # Calculate traffic discrepancy
            if traffic and domain_info["claimed_traffic"]:
                discrepancy = ((domain_info["claimed_traffic"] - traffic) / domain_info["claimed_traffic"]) * 100
                print(f"  📊 Traffic analysis: {traffic:,} actual vs {domain_info['claimed_traffic']:,} claimed ({discrepancy:+.1f}% difference)")
            
            # Create domain
            new_domain = Domain(
                domain=domain,
                domain_rating=dr,
                organic_traffic=traffic,
                referring_domains=refdomains,
                backlinks_count=backlinks,
                status=DomainStatus.ANALYZED,
                last_analyzed_at=datetime.utcnow(),
                is_adult=True,  # Escort sites
                category="Escort Directory",
                tags=f"{domain_info['region']},{domain_info['languages']},escort,adult",
                owner="Ross (EmpirEscort)",
                email="collaborations@trovagnocca.com",
                telegram="@Ross8484",
                notes=domain_info["notes"],
            )
            
            db.add(new_domain)
            db.flush()
            
            # Add contact
            contact = Contact(
                domain_id=new_domain.id,
                name="Ross",
                email="collaborations@trovagnocca.com",
                social_telegram="@Ross8484",
                is_primary=True,
                source_type="telegram",
                notes="EmpirEscort network owner. Offers: do-follow, permanent, not sponsored. Min 600 words + 2 images. 10% discount for 2+ posts. Writing service +$50-75.",
            )
            db.add(contact)
            
            # Add pricing - use 1-link price as blog_price
            link_price = LinkPrice(
                domain_id=new_domain.id,
                link_type="Guest Post",
                price=float(domain_info["price_1_link"]),
                currency="USD",
                duration_months=0,  # Permanent
                notes=f"Permanent do-follow link. 1 link: ${domain_info['price_1_link']}, 2 links: ${domain_info['price_2_links']}. 10% discount for 2+ posts. Min 600 words + 2 images. Payment: PayPal, Crypto (no TRC20), Wire (advance).",
            )
            db.add(link_price)
            
            db.commit()
            
            print(f"  ✓ Added to database with contact and pricing")
            
            results.append({
                **domain_info,
                "dr": dr,
                "actual_traffic": traffic,
                "refdomains": refdomains,
                "backlinks": backlinks,
                "status": "added"
            })
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({
                **domain_info,
                "dr": None,
                "actual_traffic": None,
                "refdomains": None,
                "backlinks": None,
                "status": "error",
                "error": str(e)
            })
        
        # Rate limit: 30 req/min = 2 seconds
        if i < len(DOMAINS):
            print(f"  → Waiting 2s for rate limit...")
            await asyncio.sleep(2)
    
    db.close()
    
    # Generate summary
    print("\n" + "=" * 80)
    print("SUMMARY - EmpirEscort Network Domains")
    print("=" * 80)
    
    print(f"\n{'Domain':<20} {'DR':>4} {'Actual Traffic':>15} {'Claimed Traffic':>15} {'Diff %':>8} {'Price':>6} {'DR/$':>6}")
    print("-" * 100)
    
    for r in results:
        if r.get("status") == "error":
            continue
        
        dr = r.get("dr") or 0
        actual = r.get("actual_traffic") or 0
        claimed = r.get("claimed_traffic", 0)
        price = r.get("price_1_link", 0)
        
        # Calculate difference
        if claimed > 0:
            diff_pct = ((claimed - actual) / claimed) * 100
        else:
            diff_pct = 0
        
        # Calculate value
        dr_per_dollar = f"{dr / price:.2f}" if price > 0 else "N/A"
        
        print(f"{r['domain']:<20} {dr:>4} {actual:>15,} {claimed:>15,} {diff_pct:>7.1f}% ${price:>5} {dr_per_dollar:>6}")
    
    # Detailed analysis
    print("\n" + "=" * 80)
    print("VALUE ANALYSIS")
    print("=" * 80)
    
    valid_results = [r for r in results if r.get("dr") and r.get("status") != "error"]
    
    if valid_results:
        for r in valid_results:
            print(f"\n{r['domain'].upper()}")
            print("-" * 40)
            print(f"  Domain Rating:      {r['dr']}")
            print(f"  Actual Traffic:     {r['actual_traffic']:,} organic visits/month (Ahrefs)")
            print(f"  Claimed Traffic:    {r['claimed_traffic']:,} users/month (Ross)")
            
            if r['actual_traffic'] and r['claimed_traffic']:
                ratio = (r['actual_traffic'] / r['claimed_traffic']) * 100
                if ratio < 5:
                    verdict = "⚠️  HUGE DISCREPANCY - claimed traffic is vastly overstated"
                elif ratio < 20:
                    verdict = "⚠️  MAJOR DISCREPANCY - likely inflated claims"
                elif ratio < 50:
                    verdict = "⚠️  MODERATE DISCREPANCY - some inflation"
                elif ratio < 80:
                    verdict = "✓ REASONABLE - minor difference (acceptable)"
                else:
                    verdict = "✓ ACCURATE - claims match metrics"
                
                print(f"  Traffic Ratio:      {ratio:.1f}% of claimed")
                print(f"  Assessment:         {verdict}")
            
            print(f"  Referring Domains:  {r['refdomains']:,}")
            print(f"  Backlinks:          {r['backlinks']:,}")
            print(f"  Price (1 link):     ${r['price_1_link']}")
            print(f"  Price (2 links):    ${r['price_2_links']}")
            print(f"  DR per Dollar:      {r['dr'] / r['price_1_link']:.2f}")
            print(f"  Region:             {r['region']}")
            print(f"  Languages:          {r['languages']}")
    
    # Overall recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    if valid_results:
        avg_dr = sum(r['dr'] for r in valid_results) / len(valid_results)
        avg_price = sum(r['price_1_link'] for r in valid_results) / len(valid_results)
        avg_dr_per_dollar = avg_dr / avg_price
        
        print(f"\nAverage DR:           {avg_dr:.1f}")
        print(f"Average Price:        ${avg_price:.0f}")
        print(f"Average DR/$:         {avg_dr_per_dollar:.2f}")
        
        # Compare to Ross Bleustein's best
        print(f"\nComparison to Ross Bleustein's network:")
        print(f"  Best value (amateurporn.me): DR 54 @ $125 = 0.43 DR/$")
        print(f"  Average value:                DR 19.8 @ $116 = 0.17 DR/$")
        print(f"  EmpirEscort average:          DR {avg_dr:.1f} @ ${avg_price:.0f} = {avg_dr_per_dollar:.2f} DR/$")
        
        if avg_dr_per_dollar < 0.10:
            verdict = "⚠️  POOR VALUE - significantly overpriced vs alternatives"
        elif avg_dr_per_dollar < 0.15:
            verdict = "⚠️  BELOW AVERAGE - better options available"
        elif avg_dr_per_dollar < 0.20:
            verdict = "✓ FAIR VALUE - comparable to market"
        elif avg_dr_per_dollar < 0.30:
            verdict = "✓ GOOD VALUE - competitive pricing"
        else:
            verdict = "✓✓ EXCELLENT VALUE - highly recommended"
        
        print(f"\nOVERALL VERDICT: {verdict}")
        
        # Traffic reality check
        print(f"\nTRAFFIC CLAIMS:")
        total_actual = sum(r.get('actual_traffic', 0) for r in valid_results)
        total_claimed = sum(r.get('claimed_traffic', 0) for r in valid_results)
        
        if total_claimed > 0:
            accuracy = (total_actual / total_claimed) * 100
            print(f"  Total claimed:  {total_claimed:,} users/month")
            print(f"  Total actual:   {total_actual:,} organic visits/month")
            print(f"  Accuracy:       {accuracy:.1f}%")
            
            if accuracy < 10:
                print(f"  ⚠️  WARNING: Claimed traffic is 10x+ higher than Ahrefs shows.")
                print(f"             Either they count something else (pageviews? total users?)")
                print(f"             or the claims are significantly inflated.")
    
    print(f"\n✓ Total processed: {len(results)}")
    print(f"✓ Successfully added/updated: {len([r for r in results if r.get('dr')])}")
    errors = [r for r in results if r.get('status') == 'error']
    if errors:
        print(f"✗ Errors: {len(errors)}")
        for r in errors:
            print(f"  - {r['domain']}: {r.get('error', 'Unknown')}")


if __name__ == "__main__":
    asyncio.run(main())
