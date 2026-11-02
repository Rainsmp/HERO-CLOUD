import asyncio
import re

class SSHX:
    def __init__(self, lxd):
        self.lxd = lxd

    async def start(self, name):
        self.lxd.validate(name)
        script = r'''set -eu
command -v curl >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq curl ca-certificates)
if ! command -v sshx >/dev/null 2>&1; then curl -fsSL https://sshx.io/get | sh; fi
BIN="$(command -v sshx || true)"
[ -n "$BIN" ] || exit 31
mkdir -p /var/lib/hero-cloud
if [ -s /var/lib/hero-cloud/sshx.url ] && [ -s /var/lib/hero-cloud/sshx.pid ]; then
 P="$(cat /var/lib/hero-cloud/sshx.pid)"
 if kill -0 "$P" 2>/dev/null; then cat /var/lib/hero-cloud/sshx.url; exit 0; fi
fi
rm -f /var/lib/hero-cloud/sshx.url /var/lib/hero-cloud/sshx.pid
nohup "$BIN" --quiet --name 'HERO CLOUD VPS' >/var/lib/hero-cloud/sshx.log 2>&1 </dev/null &
echo $! >/var/lib/hero-cloud/sshx.pid
i=0
while [ "$i" -lt 45 ]; do
 U="$(grep -Eo 'https://[^[:space:]]+' /var/lib/hero-cloud/sshx.log | head -n1 || true)"
 if [ -n "$U" ]; then printf '%s' "$U" >/var/lib/hero-cloud/sshx.url; chmod 600 /var/lib/hero-cloud/sshx.url; printf '%s' "$U"; exit 0; fi
 i=$((i+1)); sleep 1
done
exit 32
'''
        result = await self.lxd.run('exec', name, '--', 'sh', '-lc', script, timeout=240)
        url = result.strip().splitlines()[-1] if result.strip() else ''
        if not re.fullmatch(r'https://[^\s]+', url):
            raise RuntimeError('SSHX did not return a valid URL')
        return url

    async def stop(self, name):
        try:
            await self.lxd.run('exec', name, '--', 'sh', '-lc',
                'if [ -s /var/lib/hero-cloud/sshx.pid ]; then kill "$(cat /var/lib/hero-cloud/sshx.pid)" 2>/dev/null || true; fi; rm -f /var/lib/hero-cloud/sshx.pid /var/lib/hero-cloud/sshx.url')
        except Exception:
            pass
