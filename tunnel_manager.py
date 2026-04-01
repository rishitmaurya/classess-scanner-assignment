"""
Tunnel Manager — Handles ngrok/cloudflare with robust fallbacks.
"""

import asyncio
import subprocess
import shutil
import sys
import os
import platform
import zipfile
import urllib.request
from pathlib import Path
from typing import Optional
import config


class TunnelManager:
    def __init__(self):
        self.public_url: Optional[str] = None
        self.tunnel_process = None
        self._pyngrok_tunnel = None

    async def start(self) -> Optional[str]:
        # 1. Manual URL
        if config.MANUAL_PUBLIC_URL:
            self.public_url = config.MANUAL_PUBLIC_URL.rstrip("/")
            print(f"\n✅ Using manual URL: {self.public_url}\n")
            return self.public_url

        # 2. Check if ngrok is already running externally
        existing = await self._detect_existing_ngrok()
        if existing:
            self.public_url = existing
            print(f"\n✅ Found existing ngrok tunnel: {self.public_url}\n")
            return self.public_url

        # 3. Try ngrok
        if config.NGROK_ENABLED:
            url = await self._start_ngrok()
            if url:
                return url

        # 4. Try cloudflare
        if config.CLOUDFLARE_ENABLED:
            url = await self._start_cloudflare()
            if url:
                return url

        self._print_help()
        return None

    async def _start_ngrok(self) -> Optional[str]:
        print("\n🔄 Starting ngrok tunnel...")

        # Method 1: pyngrok
        url = await self._try_pyngrok()
        if url:
            return url

        # Method 2: ngrok CLI (check common locations)
        url = await self._try_ngrok_cli()
        if url:
            return url

        # Method 3: Try downloading ngrok directly
        url = await self._download_and_run_ngrok()
        if url:
            return url

        return None

    async def _try_pyngrok(self) -> Optional[str]:
        try:
            from pyngrok import ngrok, conf
            from pyngrok.exception import PyngrokNgrokError

            if config.NGROK_AUTH_TOKEN:
                ngrok.set_auth_token(config.NGROK_AUTH_TOKEN)

            if config.NGROK_REGION:
                c = conf.get_default()
                c.region = config.NGROK_REGION
                conf.set_default(c)

            # Kill existing
            try:
                for t in ngrok.get_tunnels():
                    ngrok.disconnect(t.public_url)
            except Exception:
                pass

            tunnel = ngrok.connect(config.SERVER_PORT, "http")
            self._pyngrok_tunnel = tunnel
            self.public_url = tunnel.public_url
            if self.public_url.startswith("http://"):
                self.public_url = self.public_url.replace("http://", "https://")

            print(f"   ✅ pyngrok: {self.public_url}\n")
            return self.public_url

        except ImportError:
            print("   ℹ️  pyngrok not installed (pip install pyngrok)")
        except Exception as e:
            error_msg = str(e)
            if "ngrok" in error_msg.lower() and ("download" in error_msg.lower() or "500" in error_msg):
                print(f"   ❌ pyngrok can't download ngrok binary (server issue)")
                print(f"      Download manually: https://ngrok.com/download")
                # Try to use manually installed ngrok with pyngrok
                return await self._try_pyngrok_with_local_ngrok()
            else:
                print(f"   ❌ pyngrok error: {error_msg[:150]}")
        return None

    async def _try_pyngrok_with_local_ngrok(self) -> Optional[str]:
        """If pyngrok can't download ngrok, point it to a local copy."""
        ngrok_path = self._find_ngrok_binary()
        if not ngrok_path:
            return None

        try:
            from pyngrok import ngrok, conf

            c = conf.get_default()
            c.ngrok_path = str(ngrok_path)
            if config.NGROK_REGION:
                c.region = config.NGROK_REGION
            conf.set_default(c)

            if config.NGROK_AUTH_TOKEN:
                ngrok.set_auth_token(config.NGROK_AUTH_TOKEN)

            tunnel = ngrok.connect(config.SERVER_PORT, "http")
            self._pyngrok_tunnel = tunnel
            self.public_url = tunnel.public_url
            if self.public_url.startswith("http://"):
                self.public_url = self.public_url.replace("http://", "https://")

            print(f"   ✅ pyngrok (local binary): {self.public_url}\n")
            return self.public_url

        except Exception as e:
            print(f"   ❌ pyngrok with local binary failed: {str(e)[:100]}")
        return None

    def _find_ngrok_binary(self) -> Optional[Path]:
        """Search common locations for ngrok binary."""
        is_windows = platform.system() == "Windows"
        exe_name = "ngrok.exe" if is_windows else "ngrok"

        # Check PATH first
        found = shutil.which("ngrok")
        if found:
            return Path(found)

        # Common locations
        search_dirs = []
        if is_windows:
            search_dirs = [
                Path.home() / "ngrok",
                Path("C:/ngrok"),
                Path("C:/Program Files/ngrok"),
                Path("C:/Program Files (x86)/ngrok"),
                Path.home() / "Downloads",
                Path.home() / "Desktop",
                Path.cwd(),
                Path.cwd() / "ngrok",
            ]
        else:
            search_dirs = [
                Path("/usr/local/bin"),
                Path("/usr/bin"),
                Path.home() / "ngrok",
                Path.home() / "bin",
                Path.home() / "Downloads",
                Path.cwd(),
            ]

        # Also check pyngrok's default location
        try:
            from pyngrok import conf
            default_path = Path(conf.get_default().ngrok_path)
            if default_path.exists():
                return default_path
            search_dirs.append(default_path.parent)
        except Exception:
            pass

        for d in search_dirs:
            candidate = d / exe_name
            if candidate.exists():
                print(f"   📍 Found ngrok at: {candidate}")
                return candidate
            # Also check if the dir itself is the binary
            if d.exists() and d.name == exe_name:
                return d

        return None

    async def _try_ngrok_cli(self) -> Optional[str]:
        ngrok_path = self._find_ngrok_binary()
        if not ngrok_path:
            print("   ℹ️  ngrok binary not found in PATH or common locations")
            return None

        ngrok_str = str(ngrok_path)
        print(f"   📍 Using ngrok at: {ngrok_str}")

        try:
            if config.NGROK_AUTH_TOKEN:
                subprocess.run(
                    [ngrok_str, "config", "add-authtoken", config.NGROK_AUTH_TOKEN],
                    capture_output=True, timeout=10
                )

            cmd = [ngrok_str, "http", str(config.SERVER_PORT)]
            if config.NGROK_REGION:
                cmd.extend(["--region", config.NGROK_REGION])
            if config.NGROK_DOMAIN:
                cmd.extend(["--domain", config.NGROK_DOMAIN])

            self.tunnel_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            for _ in range(20):
                await asyncio.sleep(1)
                url = await self._detect_existing_ngrok()
                if url:
                    self.public_url = url
                    print(f"   ✅ ngrok CLI: {url}\n")
                    return url

            print("   ❌ ngrok started but URL not detected")
            if self.tunnel_process:
                self.tunnel_process.terminate()
                self.tunnel_process = None

        except Exception as e:
            print(f"   ❌ ngrok CLI error: {str(e)[:100]}")

        return None

    async def _download_and_run_ngrok(self) -> Optional[str]:
        """Download ngrok binary directly as last resort."""
        print("   📦 Attempting to download ngrok directly...")

        is_windows = platform.system() == "Windows"
        machine = platform.machine().lower()

        if is_windows:
            if "64" in machine or machine == "amd64":
                url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
            else:
                url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-386.zip"
            exe_name = "ngrok.exe"
        elif platform.system() == "Darwin":
            if "arm" in machine:
                url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-arm64.zip"
            else:
                url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-amd64.zip"
            exe_name = "ngrok"
        else:
            if "arm" in machine or "aarch" in machine:
                url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.zip"
            else:
                url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.zip"
            exe_name = "ngrok"

        ngrok_dir = Path.cwd() / "ngrok_bin"
        ngrok_dir.mkdir(exist_ok=True)
        zip_path = ngrok_dir / "ngrok.zip"
        exe_path = ngrok_dir / exe_name

        if exe_path.exists():
            print(f"   📍 Found previously downloaded ngrok at: {exe_path}")
        else:
            try:
                print(f"   ⬇️  Downloading from {url[:50]}...")
                urllib.request.urlretrieve(url, str(zip_path))

                with zipfile.ZipFile(str(zip_path), 'r') as zf:
                    zf.extractall(str(ngrok_dir))

                if not is_windows:
                    os.chmod(str(exe_path), 0o755)

                zip_path.unlink(missing_ok=True)
                print(f"   ✅ Downloaded to: {exe_path}")

            except Exception as e:
                print(f"   ❌ Download failed: {str(e)[:100]}")
                print(f"      Download manually from https://ngrok.com/download")
                print(f"      Place {exe_name} in: {ngrok_dir}")
                return None

        # Now run it
        try:
            ngrok_str = str(exe_path)

            if config.NGROK_AUTH_TOKEN:
                subprocess.run(
                    [ngrok_str, "config", "add-authtoken", config.NGROK_AUTH_TOKEN],
                    capture_output=True, timeout=10
                )

            cmd = [ngrok_str, "http", str(config.SERVER_PORT)]
            if config.NGROK_REGION:
                cmd.extend(["--region", config.NGROK_REGION])

            self.tunnel_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            for _ in range(20):
                await asyncio.sleep(1)
                found_url = await self._detect_existing_ngrok()
                if found_url:
                    self.public_url = found_url
                    print(f"   ✅ ngrok (downloaded): {found_url}\n")
                    return found_url

            print("   ❌ Downloaded ngrok started but URL not detected")
            print("   💡 You may need an auth token. Get one free at:")
            print("      https://dashboard.ngrok.com/get-started/your-authtoken")
            print("      Then set NGROK_AUTH_TOKEN in config.py")

            if self.tunnel_process:
                self.tunnel_process.terminate()
                self.tunnel_process = None

        except Exception as e:
            print(f"   ❌ Error running downloaded ngrok: {str(e)[:100]}")

        return None

    async def _detect_existing_ngrok(self) -> Optional[str]:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
                tunnels = resp.json().get("tunnels", [])
                for t in tunnels:
                    if t.get("proto") == "https":
                        return t["public_url"]
                if tunnels:
                    url = tunnels[0]["public_url"]
                    if url.startswith("http://"):
                        url = url.replace("http://", "https://")
                    return url
        except Exception:
            pass
        return None

    async def _start_cloudflare(self) -> Optional[str]:
        print("\n🔄 Starting Cloudflare tunnel...")
        if not shutil.which("cloudflared"):
            print("   ❌ cloudflared not installed")
            return None

        try:
            import re
            self.tunnel_process = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", f"http://localhost:{config.SERVER_PORT}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            for _ in range(30):
                await asyncio.sleep(1)
                if self.tunnel_process.stdout:
                    try:
                        line = self.tunnel_process.stdout.readline()
                        if line:
                            urls = re.findall(r'https://[^\s]+\.trycloudflare\.com', line)
                            if urls:
                                self.public_url = urls[0].rstrip("/")
                                print(f"   ✅ Cloudflare: {self.public_url}\n")
                                return self.public_url
                    except Exception:
                        pass
            print("   ❌ Cloudflare timeout")
            if self.tunnel_process:
                self.tunnel_process.terminate()
                self.tunnel_process = None
        except Exception as e:
            print(f"   ❌ Cloudflare error: {e}")
        return None

    def _print_help(self):
        print("\n⚠️  No tunnel available. Cross-network scanning won't work.")
        print("   ──────────────────────────────────────────────────")
        print("   OPTION 1: Install ngrok (easiest)")
        print("     a) Go to https://ngrok.com/download")
        print("     b) Download for your OS")
        print("     c) Sign up free → get auth token")
        print("     d) Set in config.py:")
        print('        NGROK_AUTH_TOKEN = "your_token_here"')
        print()
        print("   OPTION 2: Run ngrok manually in another terminal")
        print(f"     ngrok http {config.SERVER_PORT}")
        print("     (The app will auto-detect it)")
        print()
        print("   OPTION 3: Set a public URL manually")
        print("     In config.py:")
        print('     MANUAL_PUBLIC_URL = "https://your-url.com"')
        print()
        print("   OPTION 4: Same WiFi (no tunnel needed)")
        print("     Both devices on same WiFi, but camera needs HTTPS")
        print("   ──────────────────────────────────────────────────\n")

    def stop(self):
        if self.tunnel_process:
            try:
                self.tunnel_process.terminate()
                self.tunnel_process.wait(timeout=5)
            except Exception:
                try:
                    self.tunnel_process.kill()
                except Exception:
                    pass
            self.tunnel_process = None

        try:
            from pyngrok import ngrok
            ngrok.kill()
        except Exception:
            pass

        self.public_url = None
        self._pyngrok_tunnel = None


tunnel_manager = TunnelManager()