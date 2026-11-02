import os, asyncio, secrets, logging
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from core.db import Database
from integrations.lxd import LXD
from integrations.sshx import SSHX
from workers.expiry import run_expiry

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('hero-cloud')
OWNERS = {int(x.strip()) for x in os.getenv('OWNER_IDS','').split(',') if x.strip().isdigit()}

def embed(title, desc='', color=discord.Color.dark_purple()):
    e=discord.Embed(title=title, description=desc, color=color); e.set_footer(text='HERO CLOUD'); return e

def owner_check():
    async def check(i):
        if i.user.id not in OWNERS: raise app_commands.CheckFailure('Owner only')
        return True
    return app_commands.check(check)

class Bot(commands.Bot):
    async def setup_hook(self):
        self.db=Database(ROOT/'data'/'hero_cloud.db'); await asyncio.to_thread(self.db.init)
        self.lxd=LXD(os.getenv('LXC_PATH','/snap/bin/lxc')); self.sshx=SSHX(self.lxd)
        self.expiry_task=asyncio.create_task(run_expiry(self))
        gid=os.getenv('GUILD_ID','').strip()
        if gid:
            g=discord.Object(id=int(gid)); self.tree.copy_global_to(guild=g); synced=await self.tree.sync(guild=g)
        else: synced=await self.tree.sync()
        log.info('Synced %d slash commands',len(synced))
    async def close(self):
        if hasattr(self,'expiry_task'): self.expiry_task.cancel()
        await super().close()

intents=discord.Intents.default()
bot=Bot(command_prefix='!', intents=intents)

async def provision(uid):
    rows=await asyncio.to_thread(bot.db.all)
    if len(rows)>=int(os.getenv('MAX_VPS','100')): raise RuntimeError('Capacity limit reached')
    ram=int(os.getenv('DEFAULT_RAM_MB','1024')); cpu=int(os.getenv('DEFAULT_CPU_PERCENT','100')); disk=int(os.getenv('DEFAULT_DISK_MB','10240')); days=int(os.getenv('DEFAULT_DAYS','30'))
    name=f'hc-{uid}-{secrets.token_hex(4)}'
    await bot.lxd.create(name,ram,cpu,disk)
    try:
        await asyncio.to_thread(bot.db.add,name,uid,ram,cpu,disk,days)
        await bot.lxd.start(name)
        return name
    except Exception:
        await bot.lxd.delete(name); await asyncio.to_thread(bot.db.delete,name); raise

class Panel(discord.ui.View):
    def __init__(self, uid, name): super().__init__(timeout=None); self.uid=uid; self.name=name
    async def interaction_check(self,i):
        if i.user.id!=self.uid:
            await i.response.send_message(embed=embed('Access denied','This panel belongs to another user.',discord.Color.red()),ephemeral=True); return False
        return True
    @discord.ui.button(label='Start',style=discord.ButtonStyle.success)
    async def start(self,i,b):
        await i.response.defer(ephemeral=True)
        try:
            await bot.lxd.start(self.name); await asyncio.to_thread(bot.db.status,self.name,'running')
            url=await bot.sshx.start(self.name)
            try: await i.user.send(embed=embed('Private VPS terminal',f'[{self.name} SSHX terminal]({url})'))
            except discord.Forbidden: pass
            msg='VPS started. Check your DMs for the private terminal link.'
        except Exception: log.exception('Panel start failed'); msg='Start failed. Contact an administrator.'
        await i.followup.send(embed=embed('VPS start',msg),ephemeral=True)
    @discord.ui.button(label='Stop',style=discord.ButtonStyle.danger)
    async def stop(self,i,b):
        await i.response.defer(ephemeral=True)
        try:
            await bot.sshx.stop(self.name); await bot.lxd.stop(self.name); await asyncio.to_thread(bot.db.status,self.name,'stopped'); msg='VPS stopped.'
        except Exception: log.exception('Panel stop failed'); msg='Stop failed. Contact an administrator.'
        await i.followup.send(embed=embed('VPS stop',msg),ephemeral=True)
    @discord.ui.button(label='Stats',style=discord.ButtonStyle.primary)
    async def stats(self,i,b):
        r=await asyncio.to_thread(bot.db.get,self.name)
        if not r: return await i.response.send_message(embed=embed('Not found','VPS record missing.'),ephemeral=True)
        await i.response.send_message(embed=embed('VPS statistics',f"Status: {r['status']}\nRAM: {r['ram_mb']} MB\nCPU: {r['cpu_percent']}%\nDisk: {r['disk_mb']} MB"),ephemeral=True)

@bot.tree.command(name='help',description='Show member commands')
async def help_cmd(i): await i.response.send_message(embed=embed('HERO CLOUD','Member: `/deploy` `/myvps` `/sshx` `/start` `/stop` `/ping`'),ephemeral=True)
@bot.tree.command(name='ping',description='Check bot latency')
async def ping(i): await i.response.send_message(embed=embed('Pong',f'{round(bot.latency*1000)} ms'),ephemeral=True)
@bot.tree.command(name='deploy',description='Deploy your default VPS')
async def deploy(i):
    await i.response.defer(ephemeral=True)
    try:
        n=await provision(i.user.id); url=await bot.sshx.start(n); v=Panel(i.user.id,n)
        try: await i.user.send(embed=embed('Your VPS is ready',f'VPS: `{n}`\n[Open private SSHX terminal]({url})'),view=v); dm='Private details sent by DM.'
        except discord.Forbidden: dm='Enable DMs, then use /sshx.'
        await i.followup.send(embed=embed('VPS deployed',f'`{n}`\n{dm}',discord.Color.green()),view=v,ephemeral=True)
    except Exception: log.exception('Deploy failed'); await i.followup.send(embed=embed('Deployment failed','Could not deploy VPS. Contact an administrator.',discord.Color.red()),ephemeral=True)
@bot.tree.command(name='myvps',description='List your VPS instances')
async def myvps(i):
    rows=await asyncio.to_thread(bot.db.user,i.user.id); e=embed('Your VPS instances')
    if not rows: e.description='No VPS instances found.'
    for r in rows[:20]: e.add_field(name=r['name'],value=f"{r['status']} • {r['ram_mb']} MB RAM",inline=False)
    await i.response.send_message(embed=e,ephemeral=True)
@bot.tree.command(name='sshx',description='Get private SSHX link for your VPS')
async def sshx(i):
    await i.response.defer(ephemeral=True)
    rows=await asyncio.to_thread(bot.db.user,i.user.id)
    if not rows:
        return await i.followup.send(embed=embed('No VPS found','No VPS records are linked to your Discord account. Use `/myvps` or contact an administrator.',discord.Color.orange()),ephemeral=True)
    try:
        sent=0
        stopped=[]
        for r in rows:
            # Reconcile SQLite status with the actual LXD state.
            state=await bot.lxd.run('info',r['name'],check=False)
            if 'Status: RUNNING' not in state and 'Status: Running' not in state:
                await asyncio.to_thread(bot.db.status,r['name'],'stopped')
                stopped.append(r['name'])
                continue
            await asyncio.to_thread(bot.db.status,r['name'],'running')
            url=await bot.sshx.start(r['name'])
            await i.user.send(embed=embed('Private VPS terminal',f"VPS: `{r['name']}`\\n[Open SSHX terminal]({url})"))
            sent+=1
        if sent:
            msg=f'Sent {sent} private terminal link(s) by DM.'
            if stopped: msg+=' Some VPS instances are stopped; use `/start` first.'
            await i.followup.send(embed=embed('SSHX ready',msg),ephemeral=True)
        else:
            await i.followup.send(embed=embed('VPS stopped','Your VPS records exist, but none of the containers are running. Use `/start` first.',discord.Color.orange()),ephemeral=True)
    except discord.Forbidden:
        await i.followup.send(embed=embed('DM unavailable','Enable DMs from this server and run `/sshx` again.'),ephemeral=True)
    except Exception:
        log.exception('SSHX startup failed for user %s',i.user.id)
        await i.followup.send(embed=embed('SSHX startup failed','Automatic SSHX startup failed. Contact an administrator.',discord.Color.red()),ephemeral=True)

@bot.tree.command(name='start',description='Start your VPS')
async def start(i,name:str): await member_action(i,name,'start')
@bot.tree.command(name='stop',description='Stop your VPS')
async def stop(i,name:str): await member_action(i,name,'stop')

@bot.tree.command(name='owner-check',description='Check owner permissions')
@owner_check()
async def owner_check_cmd(i): await i.response.send_message(embed=embed('Owner verified','Authorized.'),ephemeral=True)
@bot.tree.command(name='create',description='Create a VPS for a member')
@owner_check()
async def create(i,member:discord.Member):
    await i.response.defer(ephemeral=True)
    try:
        n=await provision(member.id); url=await bot.sshx.start(n)
        try: await member.send(embed=embed('Your VPS was created',f'`{n}`\n[Open private SSHX terminal]({url})'),view=Panel(member.id,n)); note='Details sent by DM.'
        except discord.Forbidden: note='Member DMs disabled; private URL was not posted publicly.'
        await i.followup.send(embed=embed('VPS created',f'`{n}`\n{note}'),ephemeral=True)
    except Exception: log.exception('Owner create failed'); await i.followup.send(embed=embed('Create failed','Could not create VPS.',discord.Color.red()),ephemeral=True)
@bot.tree.command(name='delete-vps',description='Delete a VPS by its name')
@owner_check()
async def delete_vps(i,name:str):
    await i.response.defer(ephemeral=True)
    try:
        await bot.sshx.stop(name); await bot.lxd.delete(name); await asyncio.to_thread(bot.db.delete,name)
        msg='VPS deleted.'
    except Exception: log.exception('Delete failed'); msg='Delete failed; check administrator logs.'
    await i.followup.send(embed=embed('Delete VPS',msg),ephemeral=True)
@bot.tree.command(name='list-vps',description='List all VPS records')
@owner_check()
async def list_vps(i):
    rows=await asyncio.to_thread(bot.db.all); e=embed('All VPS',f'Total: {len(rows)}')
    for r in rows[:20]: e.add_field(name=r['name'],value=f"Owner {r['discord_id']} • {r['status']}",inline=False)
    await i.response.send_message(embed=e,ephemeral=True)
@bot.tree.command(name='extend-vps',description='Extend all VPS expiry for a member')
@owner_check()
async def extend_vps(i,member:discord.Member,days:app_commands.Range[int,1,365]):
    n=await asyncio.to_thread(bot.db.extend,member.id,int(days),False); await i.response.send_message(embed=embed('Expiry extended',f'Updated {n} VPS.'),ephemeral=True)
@bot.tree.command(name='set-expiry',description='Reset member VPS expiry from now')
@owner_check()
async def set_expiry(i,member:discord.Member,days:app_commands.Range[int,1,365]):
    n=await asyncio.to_thread(bot.db.extend,member.id,int(days),True); await i.response.send_message(embed=embed('Expiry updated',f'Updated {n} VPS.'),ephemeral=True)
@bot.tree.command(name='expiry-info',description='Show VPS expiry information')
@owner_check()
async def expiry_info(i):
    rows=await asyncio.to_thread(bot.db.all); e=embed('Expiry information')
    for r in rows[:20]: e.add_field(name=r['name'],value=r['expires_at'],inline=False)
    await i.response.send_message(embed=e,ephemeral=True)

@bot.tree.error
async def command_error(i,error):
    log.error('Command error: %s',type(error).__name__)
    if not i.response.is_done(): await i.response.send_message(embed=embed('Command error','Command failed. Check bot logs.',discord.Color.red()),ephemeral=True)

if __name__=='__main__':
    token=os.getenv('DISCORD_TOKEN','').strip()
    if not token or token.startswith('PUT_'): raise SystemExit('Set DISCORD_TOKEN in .env')
    if not OWNERS: raise SystemExit('Set OWNER_IDS in .env')
    bot.run(token)
