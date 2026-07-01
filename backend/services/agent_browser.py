"""
Agent Browser CLI wrapper for Python.
Provides async interface to agent-browser for browser automation.
"""

import asyncio
import json
import os
import shutil
from typing import Optional, Dict, Any, List
from datetime import datetime


AGENT_BROWSER_PATH = "/home/slither/.nvm/versions/node/v24.13.0/bin/agent-browser"
DEFAULT_SESSION = "backvora"
DEFAULT_TIMEOUT = 30


class AgentBrowserError(Exception):
    """Raised when agent-browser commands fail."""
    pass


class AgentBrowser:
    """
    Async wrapper around agent-browser CLI.
    
    Usage:
        browser = AgentBrowser(session="my-session")
        await browser.open("https://example.com")
        snapshot = await browser.snapshot(interactive=True)
        await browser.click("@e1")
        await browser.close()
    """
    
    def __init__(
        self,
        session: str = DEFAULT_SESSION,
        timeout: int = DEFAULT_TIMEOUT,
        headless: bool = True,  # Note: agent-browser is headless by default, use --headed to disable
        executable_path: Optional[str] = None,
    ):
        """
        Initialize agent-browser wrapper.
        
        Args:
            session: Session name for isolated browser state
            timeout: Default command timeout in seconds
            headless: Run in headless mode (default True; set False to use --headed)
            executable_path: Path to agent-browser binary (auto-detected if None)
        """
        self.session = session
        self.timeout = timeout
        self.headless = headless
        
        # Find agent-browser executable
        if executable_path:
            self.executable = executable_path
        else:
            self.executable = shutil.which("agent-browser") or AGENT_BROWSER_PATH
        
        if not os.path.exists(self.executable):
            raise AgentBrowserError(
                f"agent-browser not found at {self.executable}. "
                "Install with: npm install -g agent-browser"
            )
    
    async def _run(
        self,
        args: List[str],
        timeout: Optional[int] = None,
        check_success: bool = True,
    ) -> Dict[str, Any]:
        """
        Run agent-browser command and return result.
        
        Args:
            args: Command arguments (excluding --session)
            timeout: Override default timeout
            check_success: Raise exception on non-zero exit code
            
        Returns:
            Dict with stdout, stderr, returncode
        """
        cmd = [self.executable, "--session", self.session]
        # agent-browser is headless by default; only add --headed if headless=False
        if not self.headless:
            cmd.append("--headed")
        cmd.extend(args)
        
        timeout_val = timeout or self.timeout
        
        try:
            # Use Xvfb display for headed mode if available, fall back to current DISPLAY
            import os
            env = os.environ.copy()
            if not self.headless and os.path.exists('/tmp/.X11-unix/X99'):
                # Force X11 via Xvfb (works without a real desktop session)
                env['DISPLAY'] = ':99'
                env.pop('WAYLAND_DISPLAY', None)
                # Tell Chromium to use X11 ozone backend via agent-browser's --args
                env['AGENT_BROWSER_ARGS'] = '--ozone-platform=x11'
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_val,
            )
            
            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            
            if check_success and proc.returncode != 0:
                raise AgentBrowserError(
                    f"agent-browser command failed (exit {proc.returncode}): "
                    f"{stderr or stdout}"
                )
            
            return {
                "stdout": stdout,
                "stderr": stderr,
                "returncode": proc.returncode,
            }
        
        except asyncio.TimeoutError:
            raise AgentBrowserError(
                f"agent-browser command timed out after {timeout_val}s"
            )
    
    async def open(self, url: str, wait_load: bool = True) -> Dict[str, Any]:
        """
        Navigate to URL.
        
        Args:
            url: Target URL
            wait_load: Wait for networkidle after navigation
            
        Returns:
            Command result dict
        """
        args = ["open", url]
        if wait_load:
            # Use command chaining for efficiency
            result = await self._run(
                ["open", url, "&&", "agent-browser", "--session", self.session, "wait", "--load", "networkidle"],
                timeout=self.timeout + 10,
            )
        else:
            result = await self._run(args)
        
        return result
    
    async def snapshot(
        self,
        interactive: bool = True,
        cursor_interactive: bool = False,
        selector: Optional[str] = None,
        json_output: bool = True,
    ) -> Dict[str, Any]:
        """
        Take accessibility tree snapshot.
        
        Args:
            interactive: Include interactive elements with refs (@e1, @e2...)
            cursor_interactive: Include cursor:pointer elements
            selector: Scope to CSS selector
            json_output: Parse JSON output
            
        Returns:
            Snapshot data (parsed JSON if json_output=True, else raw text)
        """
        args = ["snapshot"]
        if interactive:
            args.append("-i")
        if cursor_interactive:
            args.append("-C")
        if selector:
            args.extend(["-s", selector])
        if json_output:
            args.append("--json")
        
        result = await self._run(args, timeout=20)
        
        if json_output:
            try:
                data = json.loads(result["stdout"])
                return data
            except json.JSONDecodeError:
                # Fall back to raw output
                return {"text": result["stdout"]}
        
        return {"text": result["stdout"]}
    
    async def click(self, ref: str, new_tab: bool = False) -> Dict[str, Any]:
        """
        Click element by ref.
        
        Args:
            ref: Element ref from snapshot (@e1, @e2...)
            new_tab: Open in new tab
            
        Returns:
            Command result
        """
        args = ["click", ref]
        if new_tab:
            args.append("--new-tab")
        
        return await self._run(args)
    
    async def fill(self, ref: str, text: str) -> Dict[str, Any]:
        """
        Fill input field (clears first, then types).
        
        Args:
            ref: Element ref from snapshot
            text: Text to fill
            
        Returns:
            Command result
        """
        return await self._run(["fill", ref, text])
    
    async def type(self, ref: str, text: str) -> Dict[str, Any]:
        """
        Type text into field without clearing.
        
        Args:
            ref: Element ref from snapshot
            text: Text to type
            
        Returns:
            Command result
        """
        return await self._run(["type", ref, text])
    
    async def select(self, ref: str, value: str) -> Dict[str, Any]:
        """
        Select dropdown option.
        
        Args:
            ref: Element ref from snapshot
            value: Option value or text
            
        Returns:
            Command result
        """
        return await self._run(["select", ref, value])
    
    async def get_text(self, ref: str = "body") -> str:
        """
        Get element text content.
        
        Args:
            ref: Element ref (default: body for full page text)
            
        Returns:
            Text content
        """
        result = await self._run(["get", "text", ref])
        return result["stdout"]
    
    async def get_url(self) -> str:
        """Get current page URL."""
        result = await self._run(["get", "url"])
        return result["stdout"]
    
    async def wait(
        self,
        selector: Optional[str] = None,
        load_state: Optional[str] = None,
        milliseconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Wait for element, load state, or time.
        
        Args:
            selector: Wait for element/ref to appear
            load_state: Wait for load state (networkidle, domcontentloaded, load)
            milliseconds: Wait fixed duration
            
        Returns:
            Command result
        """
        args = ["wait"]
        if selector:
            args.append(selector)
        if load_state:
            args.extend(["--load", load_state])
        if milliseconds:
            args.append(str(milliseconds))
        
        return await self._run(args, timeout=self.timeout + 10)
    
    async def screenshot(
        self,
        output_path: str,
        full_page: bool = False,
        annotate: bool = False,
    ) -> str:
        """
        Take screenshot.
        
        Args:
            output_path: Where to save screenshot
            full_page: Capture full page scroll
            annotate: Add numbered element labels
            
        Returns:
            Path to saved screenshot
        """
        args = ["screenshot", output_path]
        if full_page:
            args.append("--full")
        if annotate:
            args.append("--annotate")
        
        await self._run(args, timeout=30)
        return output_path
    
    async def eval_js(self, javascript: str) -> str:
        """
        Evaluate JavaScript in page context.
        
        Args:
            javascript: JavaScript code to execute
            
        Returns:
            Result as string
        """
        # Use --stdin to avoid shell quoting issues
        proc = await asyncio.create_subprocess_exec(
            self.executable,
            "--session",
            self.session,
            "eval",
            "--stdin",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=javascript.encode("utf-8")),
            timeout=self.timeout,
        )
        
        if proc.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            raise AgentBrowserError(f"JavaScript eval failed: {stderr}")
        
        return stdout_bytes.decode("utf-8", errors="replace").strip()
    
    async def find_and_click(self, text: str) -> Dict[str, Any]:
        """
        Find element by text and click it.
        
        Args:
            text: Text to search for
            
        Returns:
            Command result
        """
        return await self._run(["find", "text", text, "click"])
    
    async def find_and_fill(self, label: str, value: str) -> Dict[str, Any]:
        """
        Find input by label and fill it.
        
        Args:
            label: Label text
            value: Value to fill
            
        Returns:
            Command result
        """
        return await self._run(["find", "label", label, "fill", value])
    
    async def close(self) -> Dict[str, Any]:
        """Close browser session."""
        return await self._run(["close"], check_success=False)
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always close session."""
        try:
            await self.close()
        except Exception:
            pass  # Best effort cleanup


# Convenience function for quick tasks
async def with_browser(
    func,
    session: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
):
    """
    Run a function with a managed agent-browser instance.
    
    Usage:
        async def task(browser):
            await browser.open("https://example.com")
            return await browser.get_text()
        
        result = await with_browser(task)
    """
    session_name = session or f"backvora-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    async with AgentBrowser(session=session_name, timeout=timeout) as browser:
        return await func(browser)
