"""
CAPTCHA solving service supporting 2Captcha and CapSolver.
Tries 2Captcha first (cheaper), falls back to CapSolver.
"""

import time
from typing import Optional, Literal
import httpx


class CaptchaSolverError(Exception):
    """Raised when CAPTCHA solving fails."""
    pass


class CaptchaSolver:
    """
    CAPTCHA solver with 2Captcha and CapSolver support.
    Automatically tries 2Captcha first, falls back to CapSolver.
    """
    
    TWOCAPTCHA_KEY = "82462e4753821ae508af375d9f335e5f"
    CAPSOLVER_KEY = "CAP-CF7B5C7037F09AB42593E80D3FABB4B932EECDC1BD87EE253FBB45F201ABBF3F"
    
    TWOCAPTCHA_CREATE_URL = "https://2captcha.com/in.php"
    TWOCAPTCHA_RESULT_URL = "https://2captcha.com/res.php"
    CAPSOLVER_CREATE_URL = "https://api.capsolver.com/createTask"
    CAPSOLVER_RESULT_URL = "https://api.capsolver.com/getTaskResult"
    
    def __init__(self, timeout: int = 60):
        """
        Initialize the CAPTCHA solver.
        
        Args:
            timeout: Maximum time (in seconds) to wait for CAPTCHA solution
        """
        self.timeout = timeout
    
    async def solve(
        self, 
        site_key: str, 
        page_url: str, 
        captcha_type: Literal["recaptcha_v2", "recaptcha_v3", "hcaptcha"] = "recaptcha_v2",
        prefer_service: Optional[Literal["2captcha", "capsolver"]] = None
    ) -> str:
        """
        Solve a CAPTCHA challenge.
        
        Args:
            site_key: The site key for the CAPTCHA
            page_url: The URL of the page with the CAPTCHA
            captcha_type: Type of CAPTCHA (recaptcha_v2, recaptcha_v3, or hcaptcha)
            prefer_service: Force use of specific service (for testing)
            
        Returns:
            The solved CAPTCHA token
            
        Raises:
            CaptchaSolverError: If solving fails on all services
        """
        errors = []
        
        # Try 2Captcha first (unless CapSolver is explicitly preferred)
        if prefer_service != "capsolver":
            try:
                return await self._solve_2captcha(site_key, page_url, captcha_type)
            except Exception as e:
                errors.append(f"2Captcha failed: {str(e)}")
                if prefer_service == "2captcha":
                    raise CaptchaSolverError(f"2Captcha solving failed: {str(e)}")
        
        # Fallback to CapSolver
        if prefer_service != "2captcha":
            try:
                return await self._solve_capsolver(site_key, page_url, captcha_type)
            except Exception as e:
                errors.append(f"CapSolver failed: {str(e)}")
        
        # Both failed
        raise CaptchaSolverError(f"All CAPTCHA services failed: {'; '.join(errors)}")
    
    async def _solve_2captcha(
        self,
        site_key: str,
        page_url: str,
        captcha_type: str
    ) -> str:
        """
        Solve CAPTCHA using 2Captcha service.
        
        API docs: https://2captcha.com/2captcha-api
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Determine method based on CAPTCHA type
            if captcha_type == "recaptcha_v2":
                method = "userrecaptcha"
            elif captcha_type == "recaptcha_v3":
                method = "userrecaptcha"
                # v3 needs action parameter, but we'll use default
            elif captcha_type == "hcaptcha":
                method = "hcaptcha"
            else:
                method = "userrecaptcha"  # Default to v2
            
            # Submit CAPTCHA task
            params = {
                "key": self.TWOCAPTCHA_KEY,
                "method": method,
                "googlekey": site_key,
                "pageurl": page_url,
                "json": 1,
            }
            
            if captcha_type == "recaptcha_v3":
                params["version"] = "v3"
                params["action"] = "submit"  # Default action
                params["min_score"] = 0.3
            
            resp = await client.get(self.TWOCAPTCHA_CREATE_URL, params=params)
            data = resp.json()
            
            if data.get("status") != 1:
                raise CaptchaSolverError(f"2Captcha task creation failed: {data.get('request', 'unknown error')}")
            
            task_id = data.get("request")
            if not task_id:
                raise CaptchaSolverError("2Captcha did not return task ID")
            
            # Poll for result
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                await self._async_sleep(5)  # Wait 5 seconds between polls
                
                result_params = {
                    "key": self.TWOCAPTCHA_KEY,
                    "action": "get",
                    "id": task_id,
                    "json": 1,
                }
                
                resp = await client.get(self.TWOCAPTCHA_RESULT_URL, params=result_params)
                data = resp.json()
                
                if data.get("status") == 1:
                    token = data.get("request")
                    if token:
                        return token
                    raise CaptchaSolverError("2Captcha returned success but no token")
                
                if data.get("request") == "CAPCHA_NOT_READY":
                    continue
                
                # Any other response is an error
                if data.get("request") != "CAPCHA_NOT_READY":
                    raise CaptchaSolverError(f"2Captcha error: {data.get('request', 'unknown')}")
            
            raise CaptchaSolverError(f"2Captcha timeout after {self.timeout}s")
    
    async def _solve_capsolver(
        self,
        site_key: str,
        page_url: str,
        captcha_type: str
    ) -> str:
        """
        Solve CAPTCHA using CapSolver service.
        
        API docs: https://docs.capsolver.com/
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Determine task type
            if captcha_type == "recaptcha_v2":
                task_type = "ReCaptchaV2TaskProxyLess"
            elif captcha_type == "recaptcha_v3":
                task_type = "ReCaptchaV3TaskProxyLess"
            elif captcha_type == "hcaptcha":
                task_type = "HCaptchaTaskProxyLess"
            else:
                task_type = "ReCaptchaV2TaskProxyLess"  # Default
            
            # Create task
            task_data = {
                "clientKey": self.CAPSOLVER_KEY,
                "task": {
                    "type": task_type,
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                }
            }
            
            if captcha_type == "recaptcha_v3":
                task_data["task"]["pageAction"] = "submit"
                task_data["task"]["minScore"] = 0.3
            
            resp = await client.post(self.CAPSOLVER_CREATE_URL, json=task_data)
            data = resp.json()
            
            if data.get("errorId", 0) != 0:
                error_desc = data.get("errorDescription", "unknown error")
                # Try alternative task type for reCAPTCHA v2
                if captcha_type == "recaptcha_v2" and "Enterprise" not in task_type:
                    # Try Enterprise variant
                    task_data["task"]["type"] = "ReCaptchaV2EnterpriseTaskProxyLess"
                    resp = await client.post(self.CAPSOLVER_CREATE_URL, json=task_data)
                    data = resp.json()
                    if data.get("errorId", 0) != 0:
                        raise CaptchaSolverError(f"CapSolver task creation failed: {data.get('errorDescription', 'unknown')}")
                else:
                    raise CaptchaSolverError(f"CapSolver task creation failed: {error_desc}")
            
            task_id = data.get("taskId")
            if not task_id:
                raise CaptchaSolverError("CapSolver did not return task ID")
            
            # Poll for result
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                await self._async_sleep(3)  # CapSolver is usually faster
                
                result_data = {
                    "clientKey": self.CAPSOLVER_KEY,
                    "taskId": task_id,
                }
                
                resp = await client.post(self.CAPSOLVER_RESULT_URL, json=result_data)
                data = resp.json()
                
                status = data.get("status")
                
                if status == "ready":
                    solution = data.get("solution", {})
                    token = solution.get("gRecaptchaResponse") or solution.get("token")
                    if token:
                        return token
                    raise CaptchaSolverError("CapSolver returned ready but no token in solution")
                
                if status == "failed":
                    raise CaptchaSolverError(f"CapSolver failed: {data.get('errorDescription', 'unknown')}")
                
                # status == "processing", continue polling
            
            raise CaptchaSolverError(f"CapSolver timeout after {self.timeout}s")
    
    async def _async_sleep(self, seconds: float):
        """Async sleep helper."""
        import asyncio
        await asyncio.sleep(seconds)


async def solve_captcha(
    site_key: str,
    page_url: str,
    captcha_type: Literal["recaptcha_v2", "recaptcha_v3", "hcaptcha"] = "recaptcha_v2",
    timeout: int = 60
) -> str:
    """
    Convenience function to solve a CAPTCHA.
    
    Args:
        site_key: The site key for the CAPTCHA
        page_url: The URL of the page with the CAPTCHA
        captcha_type: Type of CAPTCHA (recaptcha_v2, recaptcha_v3, or hcaptcha)
        timeout: Maximum time to wait for solution (seconds)
        
    Returns:
        The solved CAPTCHA token
    """
    solver = CaptchaSolver(timeout=timeout)
    return await solver.solve(site_key, page_url, captcha_type)
