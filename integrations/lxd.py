import asyncio
import re

class LXD:
    def __init__(self, binary='/snap/bin/lxc'):
        self.binary = binary

    def validate(self, name):
        if not re.fullmatch(r'hc-\d+-[a-f0-9]{8}', name or ''):
            raise ValueError('Invalid VPS name')

    async def run(self, *args, timeout=300, check=True):
        proc = await asyncio.create_subprocess_exec(self.binary, *map(str, args),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill(); await proc.wait(); raise RuntimeError('LXD command timed out')
        if check and proc.returncode:
            raise RuntimeError('LXD command failed: ' + err.decode(errors='replace')[:250])
        return out.decode(errors='replace').strip()

    async def create(self, name, ram, cpu, disk):
        self.validate(name)
        await self.run('launch', 'ubuntu:jammy/amd64', name,
            '--config', f'limits.memory={int(ram)}MB',
            '--config', f'limits.cpu.allowance={int(cpu)}%')
        await self.run('config', 'device', 'set', name, 'root', 'size', f'{int(disk)}MB', check=False)

    async def start(self, name):
        self.validate(name); await self.run('start', name, check=False)

    async def stop(self, name):
        self.validate(name); await self.run('stop', name, '--timeout', '30', check=False)

    async def delete(self, name):
        self.validate(name); await self.run('delete', name, '--force')
