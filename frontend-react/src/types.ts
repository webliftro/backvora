export interface Domain {
  id: string; domain: string; domain_rating: number | null; organic_traffic: number | null;
  referring_domains: number | null; backlinks_count: number | null; is_competitor: boolean;
  is_adult: boolean; category: string | null; tags: string | null; link_types: string[];
  domain_niche?: 'adult' | 'non_adult' | 'unknown' | null; adult_method?: string | null;
  adult_confidence?: number | null; adult_detail?: string | null; adult_classified_at?: string | null;
  is_adult_overridden?: boolean; adult_override?: { verdict: string; note: string | null; root_domain: string } | null;
  status: string; notes: string | null; owner: string | null; email: string | null;
  telegram: string | null; language?: string | null; niche_tags?: string | null;
  created_at: string | null; updated_at: string | null;
  backlinks: BacklinkGroup[]; backlink_url: string | null; backlink_target: string | null;
  backlink_anchor: string | null; backlink_count: number; link_prices: LinkPrice[];
  contacts_count?: number; has_contact_info?: boolean; has_primary_contact?: boolean; has_email?: boolean; 
  has_form?: boolean; has_captcha?: boolean;
}
export interface BacklinkGroup { target: string; links: { url: string; anchor: string }[]; total: number; }
export interface Backlink { id: string; source_domain_id: string; source_url: string; target_domain: string; anchor_text: string; is_dofollow: boolean; }
export interface LinkPrice { id: string; domain_id: string; link_type: string; price: number | null; currency: string; duration_months: number | null; is_permanent: boolean; notes: string | null; }
export interface Competitor { domain: string; referring_domains: number; backlink_count: number; avg_dr: number | null; avg_traffic: number | null; }
export interface DomainListResponse { items: Domain[]; total: number; page: number; per_page: number; pages: number; }
export type DomainStatus = 'new' | 'analyzing' | 'analyzed' | 'contacted' | 'replied' | 'negotiating' | 'deal_closed' | 'rejected' | 'blacklisted';
export const DOMAIN_STATUSES: DomainStatus[] = ['new', 'analyzing', 'analyzed', 'contacted', 'replied', 'negotiating', 'deal_closed', 'rejected', 'blacklisted'];
