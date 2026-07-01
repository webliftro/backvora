"""
Add Ross Bleustein's domains to BackVora with Ahrefs metrics.
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


# Ross's domains with prices (blog post / nav-header per year)
DOMAINS = [
    ("honeyaffair.com", 250, None),
    ("escortworld.xxx", 100, 450),
    ("amateurporn.me", 125, 1000),
    ("interracialporn.xxx", 100, 875),
    ("megapornx.com", 150, 700),
    ("porngun.net", 100, 525),
    ("pornvibe.org", 100, 475),
    ("qpornx.com", 100, 450),
    ("xxxpicss.com", 100, 700),
    ("xxxpicz.com", 125, 1100),
    ("freepornpicss.com", 100, 500),
    ("nsfwsauce.com", 75, 300),
    ("xmonstercock.com", 75, 350),
    ("milfpornhome.com", 75, 350),
    ("xxxpornozone.com", 100, 500),
    ("mypornhere.com", 175, 1600),
    ("pornrewind.com", 125, 1000),
    ("pornpic.com", 125, 950),
    ("homemoviestube.com", 225, 1950),
    ("hentaiporntube.net", 100, None),
    ("overwatchporn.xxx", 100, None),
    ("teamceleb.com", 75, None),
    ("justpicsplease.com", 125, 975),
    ("pornfriday.com", 100, 650),
    ("milfzr.com", 150, 1000),
    ("momzr.com", 165, 1250),
    ("eveknows.com", 100, 650),
    ("imageweb.ws", 100, 450),
    ("hardcoreluv.com", 100, 450),
    ("hentairider.com", 125, 650),
    ("iluvtoons.com", 100, 500),
    ("older-mature.net", 100, 450),
    ("pezporn.com", 100, 450),
    ("pornstarsluv.com", 100, 450),
    ("pussyspot.net", 100, 450),
    ("tongabonga.com", 100, None),  # assuming ~$100
]


async def main():
    """Fetch metrics and add domains to database."""
    db: Session = SessionLocal()
    ahrefs = AhrefsService()
    
    results = []
    
    print(f"Processing {len(DOMAINS)} domains from Ross Bleustein...")
    print("=" * 80)
    
    for i, (domain, blog_price, header_price) in enumerate(DOMAINS, 1):
        print(f"\n[{i}/{len(DOMAINS)}] {domain}")
        
        # Check if domain already exists
        existing = db.query(Domain).filter(Domain.domain == domain).first()
        if existing:
            print(f"  ⚠️  Domain already exists (ID: {existing.id})")
            # Still fetch metrics if needed
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
                    print(f"  ✓ Updated metrics: DR={metrics.get('domain_rating')}, Traffic={metrics.get('organic_traffic')}")
                    results.append({
                        "domain": domain,
                        "dr": metrics.get("domain_rating"),
                        "traffic": metrics.get("organic_traffic"),
                        "refdomains": metrics.get("referring_domains"),
                        "blog_price": blog_price,
                        "header_price": header_price,
                        "status": "updated_existing"
                    })
                except Exception as e:
                    print(f"  ✗ Error fetching metrics: {e}")
                    results.append({
                        "domain": domain,
                        "dr": existing.domain_rating,
                        "traffic": existing.organic_traffic,
                        "refdomains": existing.referring_domains,
                        "blog_price": blog_price,
                        "header_price": header_price,
                        "status": "existing_no_update",
                        "error": str(e)
                    })
            else:
                results.append({
                    "domain": domain,
                    "dr": existing.domain_rating,
                    "traffic": existing.organic_traffic,
                    "refdomains": existing.referring_domains,
                    "blog_price": blog_price,
                    "header_price": header_price,
                    "status": "existing"
                })
            
            # Rate limit
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
            
            print(f"  ✓ DR={dr}, Traffic={traffic}, RefDomains={refdomains}, Backlinks={backlinks}")
            
            # Create domain
            new_domain = Domain(
                domain=domain,
                domain_rating=dr,
                organic_traffic=traffic,
                referring_domains=refdomains,
                backlinks_count=backlinks,
                status=DomainStatus.ANALYZED,
                last_analyzed_at=datetime.utcnow(),
                is_adult=True,  # All Ross's domains are adult
                owner="Ross Bleustein",
                email="rossbleustein@gmail.com",
                notes="Contact from email. Prices from Feb 2026 outreach.",
            )
            
            db.add(new_domain)
            db.flush()  # Get the ID
            
            # Add contact
            contact = Contact(
                domain_id=new_domain.id,
                name="Ross Bleustein",
                email="rossbleustein@gmail.com",
                is_primary=True,
                source_type="email",
            )
            db.add(contact)
            
            # Add blog post price
            blog_link = LinkPrice(
                domain_id=new_domain.id,
                link_type="Guest Post",
                price=float(blog_price),
                currency="USD",
                duration_months=12,
                notes="Blog post placement, 12 months",
            )
            db.add(blog_link)
            
            # Add header link price if available
            if header_price:
                header_link = LinkPrice(
                    domain_id=new_domain.id,
                    link_type="Header Link",
                    price=float(header_price),
                    currency="USD",
                    duration_months=12,
                    notes="Navigation header link, 12 months",
                )
                db.add(header_link)
            
            db.commit()
            
            print(f"  ✓ Added to database with contact and pricing")
            
            results.append({
                "domain": domain,
                "dr": dr,
                "traffic": traffic,
                "refdomains": refdomains,
                "blog_price": blog_price,
                "header_price": header_price,
                "status": "added"
            })
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({
                "domain": domain,
                "dr": None,
                "traffic": None,
                "refdomains": None,
                "blog_price": blog_price,
                "header_price": header_price,
                "status": "error",
                "error": str(e)
            })
        
        # Rate limit: 30 req/min = 2 seconds between requests
        if i < len(DOMAINS):
            print(f"  → Waiting 2s for rate limit...")
            await asyncio.sleep(2)
    
    db.close()
    
    # Print summary table
    print("\n" + "=" * 80)
    print("SUMMARY - Ross Bleustein's Domains")
    print("=" * 80)
    
    # Sort by best value (DR/price ratio)
    valid_results = [r for r in results if r.get("dr") and r.get("blog_price")]
    valid_results.sort(key=lambda x: x["dr"] / x["blog_price"], reverse=True)
    
    print(f"\n{'Domain':<25} {'DR':>4} {'Traffic':>8} {'RefDom':>7} {'Blog$':>6} {'Header$':>8} {'DR/$':>6} {'Status':<15}")
    print("-" * 100)
    
    for r in valid_results:
        dr_per_dollar = f"{r['dr'] / r['blog_price']:.2f}" if r.get('dr') and r.get('blog_price') else "N/A"
        header = f"${r['header_price']}" if r.get('header_price') else "N/A"
        traffic = r.get('traffic') or 0
        refdomains = r.get('refdomains') or 0
        
        print(f"{r['domain']:<25} {r['dr']:>4} {traffic:>8,} {refdomains:>7,} ${r['blog_price']:>5} {header:>8} {dr_per_dollar:>6} {r['status']:<15}")
    
    # Show errors
    errors = [r for r in results if r.get("status") == "error"]
    if errors:
        print(f"\n{len(errors)} domains had errors:")
        for r in errors:
            print(f"  ✗ {r['domain']}: {r.get('error', 'Unknown error')}")
    
    print(f"\n✓ Total processed: {len(results)}")
    print(f"✓ Successfully added/updated: {len([r for r in results if r.get('dr')])}")
    print(f"✓ Errors: {len(errors)}")
    
    # Top 10 by value
    print(f"\n🏆 TOP 10 BY VALUE (DR per dollar):")
    print("-" * 80)
    for i, r in enumerate(valid_results[:10], 1):
        dr_per_dollar = r['dr'] / r['blog_price']
        print(f"{i:2}. {r['domain']:<25} DR {r['dr']:>3} @ ${r['blog_price']:>3} = {dr_per_dollar:.2f} DR/$")


if __name__ == "__main__":
    asyncio.run(main())
