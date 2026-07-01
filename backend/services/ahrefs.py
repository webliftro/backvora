"""
Ahrefs MCP service - interface with Ahrefs API via MCP protocol.
"""

import httpx
from typing import Any, Optional
from datetime import date, timedelta

from ..config import settings


class AhrefsError(Exception):
    """Ahrefs API error."""
    pass


class AhrefsService:
    """Service for interacting with Ahrefs MCP API."""
    
    def __init__(self):
        self.api_key = settings.ahrefs_api_key
        self.mcp_url = settings.ahrefs_mcp_url
        
        if not self.api_key:
            raise AhrefsError("AHREFS_API_KEY not configured")
    
    async def _call_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Call an Ahrefs MCP tool.
        
        Args:
            tool_name: Name of the Ahrefs tool
            params: Parameters for the tool
            
        Returns:
            Tool response data
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.mcp_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": params,
                    },
                },
            )
            
            if response.status_code != 200:
                raise AhrefsError(f"API error: {response.status_code} - {response.text}")
            
            result = response.json()
            
            if "error" in result:
                raise AhrefsError(f"MCP error: {result['error']}")
            
            # Extract text content from MCP response
            content = result.get("result", {}).get("content", [])
            if content and len(content) > 0:
                import json
                text = content[0].get("text", "{}")
                return json.loads(text)
            
            return result
    
    async def get_domain_metrics(self, domain: str) -> dict[str, Any]:
        """
        Get overview metrics for a domain.
        
        Args:
            domain: Domain to analyze
            
        Returns:
            Dict with domain_rating, organic_traffic, etc.
        """
        # Ahrefs data lags ~2-3 days; use 3 days ago to avoid "bad date" errors
        today = (date.today() - timedelta(days=3)).isoformat()
        
        # Get domain rating
        dr_result = await self._call_tool("site-explorer-domain-rating", {
            "target": domain,
            "date": today,
        })
        
        # Get traffic metrics
        metrics_result = await self._call_tool("site-explorer-metrics", {
            "target": domain,
            "mode": "subdomains",
            "date": today,
        })
        
        # Get backlinks stats (refdomains + backlinks count)
        backlinks_stats = await self._call_tool("site-explorer-backlinks-stats", {
            "target": domain,
            "mode": "subdomains",
            "date": today,
        })
        
        # Combine results
        dr_data = dr_result.get("domain_rating", {})
        metrics_data = metrics_result.get("metrics", {})
        bl_data = backlinks_stats.get("metrics", {})
        
        return {
            "domain": domain,
            "domain_rating": dr_data.get("domain_rating"),
            "ahrefs_rank": dr_data.get("ahrefs_rank"),
            "organic_traffic": metrics_data.get("org_traffic"),
            "organic_keywords": metrics_data.get("org_keywords"),
            "referring_domains": bl_data.get("live_refdomains"),
            "backlinks_count": bl_data.get("live"),
        }
    
    async def get_backlinks(
        self, 
        domain: str, 
        limit: int = 100,
        mode: str = "subdomains",
    ) -> list[dict[str, Any]]:
        """
        Get backlinks pointing to a domain.
        
        Args:
            domain: Target domain
            limit: Max number of backlinks to fetch
            mode: subdomains, domain, exact, prefix
            
        Returns:
            List of backlink records
        """
        all_backlinks = []
        offset = 0
        page_size = min(limit, 50)  # Ahrefs seems to cap around 50
        
        while len(all_backlinks) < limit:
            result = await self._call_tool("site-explorer-all-backlinks", {
                "target": domain,
                "mode": mode,
                "limit": page_size,
                "offset": offset,
                "select": "name_source,url_from,url_to,anchor,domain_rating_source,url_rating_source,traffic_domain,is_dofollow,first_seen,last_seen",
            })
            
            backlinks = result.get("backlinks", [])
            if not backlinks:
                break  # No more results
            
            all_backlinks.extend(backlinks)
            offset += len(backlinks)
            
            if len(backlinks) < page_size:
                break  # Last page
        
        return all_backlinks[:limit]
    
    async def get_referring_domains(
        self, 
        domain: str, 
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get referring domains for a target domain (one per domain).
        
        Args:
            domain: Target domain
            limit: Max number of referring domains
            
        Returns:
            List of referring domain records
        """
        # Use all-backlinks sorted by domain traffic
        result = await self._call_tool("site-explorer-all-backlinks", {
            "target": domain,
            "mode": "subdomains",
            "limit": limit,
            "select": "name_source,domain_rating_source,traffic_domain,url_from,anchor,is_dofollow,first_seen,last_seen",
            "order_by": "traffic_domain:desc",
            "aggregation": "1_per_domain",
        })
        
        return result.get("backlinks", [])
    
    async def get_anchor_distribution(
        self,
        domain: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get anchor text distribution for backlinks.
        
        Args:
            domain: Target domain
            limit: Max number of anchors
            
        Returns:
            List of anchor records with counts
        """
        result = await self._call_tool("site-explorer-anchors", {
            "target": domain,
            "mode": "subdomains",
            "limit": limit,
            "select": "anchor,links_to_target,refdomains,dofollow_links,first_seen,last_seen",
            "order_by": "links_to_target:desc",
        })
        
        return result.get("anchors", [])
    
    async def check_usage(self) -> dict[str, Any]:
        """
        Check API usage and limits.
        
        Returns:
            Usage information
        """
        result = await self._call_tool("subscription-info-limits-and-usage", {})
        return result.get("limits_and_usage", result)
