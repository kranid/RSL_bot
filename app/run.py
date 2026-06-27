import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer, PRODUCTION
from aiogram.client.session.base import BaseSession

from aiohttp import web

from core.commands_bot_utils import BOT_COMMANDS
from core.settings import settings
from handlers import create_user_router, admin_router, superadmin_router
from core.database.database_helper import DatabaseHelper
from core.limiter import Limiter
from middlewares.permission_middleware import PermissionMiddleware


async def _handle_health(request: web.Request) -> web.Response:
    return web.Response(text="Service is available", status=200)


async def start_health_server(host:str="0.0.0.0", port:int=8090) -> None:
    app = web.Application()
    app.router.add_get("/health", _handle_health)
    app.router.add_get("/healthz", _handle_health)
    app.router.add_get("/readyz", _handle_health)
    app.router.add_get("/livez", _handle_health)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host, port)
    await site.start()
    logging.getLogger().info(f"Health server started at http://{host}:{port}/health, http://{host}:{port}/healthz, http://{host}:{port}/readyz, http://{host}:{port}/livez")


async def main():
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d][P%(process)d][T%(thread)d][%(name)s] %(message)s')
    logger = logging.getLogger(__name__)
    logger.info('Logging initialized')
    logging.getLogger('aiohttp.access').setLevel(logging.WARN)

    await DatabaseHelper()
    Limiter.init(settings.limits)

    custom_api_url = os.environ.get("TELEGRAM_CUSTOM_API_URL", default=None)
    proxy = os.environ.get('HTTPS_PROXY', None)

    if proxy is not None:
        logger.info(f'Using proxy {proxy} for TG bot')

    api_server:TelegramAPIServer = PRODUCTION
    if custom_api_url is not None:
        logger.info(f'Using custom API URL {custom_api_url} for TG bot')
        api_server = TelegramAPIServer.from_base(custom_api_url)

    bot_session = AiohttpSession(
        api=api_server,
        proxy=proxy
    )
    bot_session._connector_init['ssl'] = False

    bot = Bot(
        token=settings.tg.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=bot_session
    )

    user_router = await create_user_router()

    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(superadmin_router)
    dp.include_router(user_router)
    dp.message.middleware(PermissionMiddleware(router_roles={
        user_router: ["user", "admin", "superadmin"],
        admin_router: ["admin", "superadmin"],
        superadmin_router: ["superadmin"]
    }))

    commands_for_bot = []
    for command in BOT_COMMANDS:
        commands_for_bot.append(BotCommand(command=command[0], description=command[1]))

    await bot.set_my_commands(commands=commands_for_bot)
    await bot.delete_webhook(drop_pending_updates=True)

    await start_health_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
