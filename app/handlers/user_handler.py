# TODO: di для создания http_manager с параметре handler
# TODO: Асинхронный HTTP manager
# TODO: Вынести клавиутуры в отдельный файл
# TODO: Вынести сообщения в отдельный файл
# TODO: Добавить линтеры и pre-commit hook
# TODO: Добавить middleware для логирования

import asyncio
import aiohttp
import logging
import time

from aiogram import F, Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from pydantic import ValidationError

from core.database.database_helper import DatabaseHelper
from core.limiter import Limiter
from core.settings import settings
from core.throttling import Cooldown
from core.utils import check_media_limits, check_valid_content_type, get_content_type, is_admin, limiter_reject_text
from keyboards.inline_keyboards import model_response_actions
from managers.message_manager import TypeStates

from coordinator.coordinator_client import *


async def create_user_router() -> Router:
    user_router = Router()
    callback_router = Router()
    user_router.include_router(callback_router)

    coordinator_client = CoordinatorClient(base_url=settings.coordinator.url, api_key=settings.coordinator.key)

    @user_router.message(CommandStart())
    async def command_start_handler(message: Message, state: FSMContext, command: CommandObject) -> None:
        await state.clear()
        assert message.from_user is not None

        welcome_text = (
            "Добро пожаловать! \nЯ бот для перевода русского жестового языка.\n"
            "Запишите кружочек или отправьте видеофайл для тестирования ML модели "
        )
        provided_code = (command.args or "").strip()
        current_role = await DatabaseHelper.instance().get_user_role(message.from_user.id)

        if current_role is not None:
            await DatabaseHelper.instance().add_user_or_update(
                message.from_user.id, message.from_user.username, role=None
            )
            await message.answer(welcome_text)
            return

        if provided_code == settings.tg.invite_code:
            await DatabaseHelper.instance().add_user_or_update(
                message.from_user.id,
                message.from_user.username,
                role="user",
                manual_flg=True,
            )
            await message.answer(welcome_text)
            return

        # без кода или неверный код -> роль не выдаём; заявка на одобрение будет в коммите 2
        await DatabaseHelper.instance().add_user_or_update(
            message.from_user.id, message.from_user.username, role=None
        )
        await message.answer(
            "Здравствуйте! Доступ к боту выдаётся по приглашению.\n"
            "Если у вас есть пригласительная ссылка — перейдите по ней. "
            "Либо дождитесь одобрения заявки администратором."
        )


    @user_router.message(TypeStates.send_video, F.text == "🔙 Назад")
    async def clear_context(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            text="Видео не было отправлено", reply_markup=ReplyKeyboardRemove()
        )


    @callback_router.callback_query(F.data == "regen")
    async def handle_regen(call: CallbackQuery, state: FSMContext):
        assert isinstance(call.message, Message)
        await call.message.answer("Перегенерация…")
        await download_video_file_handler(
            call.message.reply_to_message, state, regen=True
        )


    @user_router.message()
    async def download_video_file_handler(
        message: Message,
        state: FSMContext,
        regen=False,
    ) -> None:
        logger = logging.getLogger(__name__)

        media_limit_error = check_media_limits(message)
        if media_limit_error:
            await message.answer(media_limit_error)
            return

        content_type: str = get_content_type(message)
        if not regen and not check_valid_content_type(
            content_type, settings.tg.valid_content_types
        ):
            await message.answer(
                "Бот может работать только с видео файлами. "
                "Запишите кружочек или отправьте уже готовое видео :)"
            )
            return

        assert message.from_user is not None
        user_id = message.from_user.id

        remaining = Cooldown.instance().hit(user_id)
        if remaining > 0:
            await message.answer(
                f"Не так часто, пожалуйста. Подождите ещё {int(remaining) + 1} сек."
            )
            return

        async def _notify_queue() -> None:
            await message.answer("⏳ Система загружена, ваш запрос в очереди…")

        async with Limiter.instance().acquire(user_id, on_enqueue=_notify_queue) as out:
            if not out.acquired:
                await message.answer(limiter_reject_text(out.decision))
                return

            if message.video is not None:
                video_file_obj = message.video
                file_name = message.video.file_name
            elif message.video_note is not None:
                video_file_obj = message.video_note
                file_name = "_videonote.mp4"
            elif message.animation is not None:
                video_file_obj = message.animation
                file_name = message.animation.file_name
            else:
                raise Exception("No video file provided")
            if file_name is None:
                file_name = "_video.mp4"
            file_id = video_file_obj.file_id
            assert message.bot is not None
            file = await message.bot.get_file(file_id)
            file_path: str | None = file.file_path
            assert file_path is not None
            assert video_file_obj.bot is not None
            file_stream = await video_file_obj.bot.download_file(
                file_path, timeout=300
            )
            assert file_stream is not None
            if not regen:
                await message.answer(text="Видео получено! Запускаем обработку...")
            # необязательная мета-информация в dev-режиме
            generate_request = GenerateRequestV4(
                trace_id=f"bot file {video_file_obj.file_id}",
                mode="rsl:infer",
                files=[
                    SourceFile(type=FileType.video, name=file_name)
                ],
                model_params={
                    "regen": regen,
                    "dev_meta": message.caption if is_admin(await DatabaseHelper.instance().get_user_role(message.from_user.id)) else None
                },
                deadline_seconds=settings.coordinator.task_deadline_seconds,
            )
            try:
                generate_resp: GenerateResponse = await coordinator_client.generate_v4(req=generate_request, files=[file_stream])
            except asyncio.TimeoutError:
                logger.exception("Timed out while sending video to coordinator")
                await message.reply("Не удалось отправить видео на обработку: сервис не ответил вовремя. Попробуйте позже или отправьте более короткое видео.")
                return
            except aiohttp.ClientError:
                logger.exception("Coordinator request failed while starting task")
                await message.reply("Не удалось связаться с сервисом обработки. Попробуйте позже.")
                return
            except ValidationError:
                logger.exception("Coordinator returned invalid response while starting task")
                await message.reply("Сервис обработки вернул некорректный ответ. Попробуйте позже.")
                return
            if generate_resp.result != GenerateResult.accepted:
                logger.error(f"Error starting task! {generate_resp.result}")
                await message.reply("Не удалось запустить обработку! Пожалуйста, попробуйте заново!")
                return
            logger.info(f"Request task id: {generate_resp.query_id} ready estimation {generate_resp.ready_estimation_seconds}")
            assert generate_resp.query_id is not None
            assert generate_resp.ready_estimation_seconds is not None
            query_id = generate_resp.query_id
            time_start = time.perf_counter()
            wait_for = min(max(generate_resp.ready_estimation_seconds / 2, settings.coordinator.min_polling_interval_seconds), settings.coordinator.max_polling_interval_seconds)
            while True:
                logger.info(f"waiting for {wait_for}")
                await asyncio.sleep(wait_for)
                try:
                    result: GetResultResponse = await coordinator_client.get_result(req=GetResultRequest(query_id=query_id))
                except asyncio.TimeoutError:
                    logger.exception("Timed out while polling coordinator result")
                    await message.reply("Сервис обработки не ответил вовремя при получении результата. Попробуйте позже.")
                    return
                except aiohttp.ClientError:
                    logger.exception("Coordinator request failed while polling result")
                    await message.reply("Не удалось получить результат от сервиса обработки. Попробуйте позже.")
                    return
                except ValidationError:
                    logger.exception("Coordinator returned invalid response while polling result")
                    await message.reply("Сервис обработки вернул некорректный ответ. Попробуйте позже.")
                    return
                match result.status:
                    case ResultStatus.cancelled:
                        logger.warning(f"request {query_id} was cancelled")
                        await message.reply("Запрос отменен! Пожалуйста, попробуйте заново!")
                        break
                    case ResultStatus.pending:
                        assert result.ready_estimation_seconds is not None
                        logger.info(f"Request {query_id} is pending, ready estimation is {result.ready_estimation_seconds}")
                        wait_for = min(max(result.ready_estimation_seconds / 2, settings.coordinator.min_polling_interval_seconds), settings.coordinator.max_polling_interval_seconds)
                        if time.perf_counter() - time_start > settings.coordinator.task_deadline_seconds * 1.5:
                            logger.warning(f"request {query_id} timed out")
                            try:
                                await coordinator_client.cancel(req=CancelRequest(query_id=query_id))
                            except Exception:
                                logger.warning(f"failed to cancel request {query_id} after timeout", exc_info=True)
                            await message.reply("Запрос не успел выполниться вовремя и был отменен. Пожалуйста, попробуйте заново!")
                            break
                    case ResultStatus.ready:
                        text: str | None = None
                        if result.result_json is not None:
                            text = result.result_json.get("text", None)
                        if text is not None:
                            message_reply = f"Видео обработано ✅\nРаспознанный текст: {text}"
                        else:
                            message_reply = "Не удалось распознать текст :(\nПопробуйте использовать другое видео 🙏"
                        logger.info(f"Processing request {query_id} took {time.perf_counter() - time_start}s")
                        if (
                            is_admin(
                                await DatabaseHelper.instance().get_user_role(message.from_user.id)
                            )
                            and text is not None
                        ):
                            await message.reply(
                                message_reply, reply_markup=model_response_actions
                            )
                        else:
                            await message.reply(message_reply)
                        break
                    case _:
                        logger.warning(f"Got unexpected status {result.status} for request {query_id}")
    return user_router
