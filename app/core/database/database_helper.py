import logging
from typing import Optional, cast
from dataclasses import dataclass
import asyncpg
from asyncpg.connect_utils import SessionAttribute

from exceptions.database_exceptions import CantChangeHigherAccessRole, UserNotFoundException
from core.settings import settings


class DatabaseHelper:
    __instance:"DatabaseHelper"

    def __init__(self):
        self.__logger = logging.getLogger('database')

    def __await__(self):
        return self.__init_async().__await__()

    async def __init_async(self) -> "DatabaseHelper":
        self.__logger.info(
            "Creating pool, hosts = %s, port = %s, user = %s, db = %s",
            ", ".join(settings.database.hosts),
            settings.database.port,
            settings.database.user,
            settings.database.db,
        )
        self.__pool = await asyncpg.create_pool(
            host=settings.database.hosts, port=settings.database.port,
            user=settings.database.user, password=settings.database.password,
            target_session_attrs=SessionAttribute.read_write,
            timeout=5,
            min_size=1, max_size=10
        )

        self.__logger.info('Checking connection')
        await self.__check_db_connection()

        DatabaseHelper.__instance = self
        return self
    
    @staticmethod
    def instance() -> "DatabaseHelper":
        return DatabaseHelper.__instance

    async def __check_db_connection(self) -> None:
        await self.__pool.execute('select 1')

    async def add_user(self, tg_id: int, role: str, username: Optional[str] = None) -> None:
        await self.__pool.execute(
            """
                insert into users (tg_id, username, role, date_created, date_role_set)
                values ($1, $2, $3, current_timestamp, current_timestamp)
            """,
            tg_id, username, role
        )

    async def update_username(self, tg_id: int, username: str) -> None:
        await self.__pool.execute(
            """
                update users
                set username = $1
                where tg_id = $2
            """,
            username, tg_id
        )

    async def select_user_data(self, tg_id: int) -> Optional[tuple[int, str, str]]:
        row = await self.__pool.fetchrow(
            """
                select u.tg_id, u.username, u.role
                from users u
                where u.tg_id = $1
            """,
            tg_id
        )

        if row == None:
            return None
        else:
            return (row['tg_id'], row['username'], row['role'])

    async def add_user_or_update(
        self,
        tg_id: int,
        username: Optional[str] = None,
        role: Optional[str] = None,
        manual_flg: Optional[bool] = False,
    ) -> None:
        db_data = await self.select_user_data(tg_id)
        if db_data is not None:
            db_tg_id, db_username, db_role = db_data
            if role and db_role != role and manual_flg:
                await self.update_role(tg_id, role)
            if not db_username and username:
                await self.update_username(tg_id, username)
        else:
            #assert role is not None
            await self.add_user(tg_id, username=username, role=role)

    async def delete_user(self, tg_id: int):
        user_data = await self.select_user_data(tg_id)
        if not user_data:
            raise UserNotFoundException(tg_id)
        if user_data[2] != "user":
            raise CantChangeHigherAccessRole
        
        await self.update_role(tg_id, None)

    async def get_user_role(self, tg_id: int) -> str|None:
        return await self.__pool.fetchval(
            """
                select u.role
                from users u
                where u.tg_id = $1
            """, 
            tg_id
        )

    async def update_role(self, tg_id: int, role_name: Optional[str]):
        await self.__pool.execute(
            """
                update users
                set role = $1, date_role_set = current_timestamp
                where tg_id = $2
            """, 
            role_name, tg_id
        )

    async def select_users(self) -> list[tuple[int, str, str]]:
        rows = await self.__pool.fetch(
            """
                select u.tg_id, u.username, u.role
                from users u
                where u.role in ('user', 'admin', 'superadmin')
                order by u.username
            """
        )
        users_list: list[tuple[int, str, str]] = [(row['tg_id'], row['username'], row['role']) for row in rows]
        return users_list
