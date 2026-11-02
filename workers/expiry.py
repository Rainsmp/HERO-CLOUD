import asyncio
import logging
log = logging.getLogger('hero-cloud.expiry')

async def run_expiry(bot):
    while True:
        try:
            rows = await asyncio.to_thread(bot.db.expired)
            for row in rows:
                try:
                    await bot.sshx.stop(row['name'])
                    await bot.lxd.delete(row['name'])
                    await asyncio.to_thread(bot.db.delete, row['name'])
                    log.info('Removed expired VPS %s', row['name'])
                except Exception:
                    log.exception('Expiry cleanup failed for %s', row['name'])
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Expiry worker error')
        await asyncio.sleep(60)
