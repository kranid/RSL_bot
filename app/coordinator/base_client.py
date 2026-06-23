import logging
import aiohttp
import asyncio
from pydantic import BaseModel
from typing import BinaryIO, cast
from typing_extensions import Self

class BaseClient:
    def __init__(
            self, 
            base_url:str, 
            api_key:str,
            http_timeout:aiohttp.ClientTimeout|None=None,
            max_retries:int = 3,
            delay_between_retries_seconds:float = 1.0,
            get_file_timeout:aiohttp.ClientTimeout|None=None
        ):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._max_retries = max_retries
        assert self._max_retries >= 0
        self._delay_between_retries_seconds = delay_between_retries_seconds
        self._http_timeout = http_timeout
        self._get_file_timeout = get_file_timeout
        self._api_key = api_key
        self._base_url = base_url
        if not self._base_url.endswith("/"):
            self._base_url = self._base_url + "/"
        self._session = aiohttp.ClientSession()

    async def __aenter__(self) -> Self:
        await self._session.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._session.__aexit__(exc_type, exc_val, exc_tb)

    async def close(self):
        await self._session.close()

    def _should_retry(self, ex:Exception) -> bool:
        if isinstance(ex, aiohttp.ClientConnectionError):
            return True
        elif isinstance(ex, aiohttp.ClientResponseError):
            response_error = cast(aiohttp.ClientResponseError, ex)
            if response_error.status is None:
                return False
            return (response_error.status == 429 #Too many requests
                or response_error.status >= 500
            )
        else:
            return False

    async def _post_json_with_retries(self, path:str, req:BaseModel, x_request_id:str|None, max_retries:int|None, expect_result:bool) -> str|None:
        if max_retries is None:
            max_retries = self._max_retries
        else:
            assert max_retries >= 0
        max_attempts = max_retries + 1
        attempt = 0
        while attempt < max_attempts:
            try:
                attempt += 1
                return await self._post_json(path=path, req=req, x_request_id=x_request_id, expect_result=expect_result)
            except Exception as ex:
                self._logger.info(f"Attempt {attempt}/{max_attempts} of POSTing to {path} failed: {ex}")
                if self._should_retry(ex):
                    if attempt >= max_attempts:
                        self._logger.error(f"Max retries reached. Raising exception. {ex}") 
                        raise 
                    else:
                        delay = self._delay_between_retries_seconds * attempt
                        self._logger.debug(f"Waiting for {delay} seconds") 
                        await asyncio.sleep(delay)    
                else:
                    raise
        assert False

    async def _post_json(self, path:str, req:BaseModel, x_request_id:str|None, expect_result:bool) -> str|None:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }        
        if x_request_id is not None:
            headers["X-Request-ID"] = x_request_id

        full_path = self._base_url + path
        self._logger.info(f"sending coord request to {full_path}")
        async with self._session.post(full_path, data=req.model_dump_json(exclude_unset=True, exclude_none=True), headers=headers, timeout=self._http_timeout, ssl=False) as response:
            await self._check_response_errors(response=response)
            if expect_result:
                text = await response.text()
                return text
            else:
                return None
        
    async def _post_multipart_with_retries(self, path:str, req:BaseModel, files:list[BinaryIO]|None, file_names:list[str]|None, x_request_id:str|None, max_retries:int|None, expect_result:bool) -> str|None:
        if max_retries is None:
            max_retries = self._max_retries
        else:
            assert max_retries >= 0
        max_attempts = max_retries + 1
        attempt = 0
        while attempt < max_attempts:
            try:
                attempt += 1
                return await self._post_multipart(path=path, req=req, files=files, file_names=file_names, x_request_id=x_request_id, expect_result=expect_result)
            except Exception as ex:
                self._logger.info(f"Attempt {attempt}/{max_attempts} of POSTing to {path} failed: {ex}")
                if self._should_retry(ex):
                    if attempt >= max_attempts:
                        self._logger.error(f"Max retries reached. Raising exception. {ex}") 
                        raise 
                    else:
                        delay = self._delay_between_retries_seconds * attempt
                        self._logger.debug(f"Waiting for {delay} seconds") 
                        await asyncio.sleep(delay)    
                else:
                    raise
        assert False

    async def _post_multipart(self, path:str, req:BaseModel, files:list[BinaryIO]|None, file_names:list[str]|None, x_request_id:str|None, expect_result:bool) -> str|None:
        headers = {
            "Authorization": f"Bearer {self._api_key}"
        }
        if x_request_id is not None:
            headers["X-Request-ID"] = x_request_id
        full_path = self._base_url + path
        self._logger.info(f"sending coord request to {full_path}")
        with aiohttp.MultipartWriter(subtype="form-data") as mp:
            mp.append(req.model_dump_json(exclude_unset=True, exclude_none=True))
            if files is None:
                assert file_names is None
            else:
                assert file_names is not None
                assert len(files) == len(file_names)
                for file_index in range(0, len(files)):
                    doc_part = mp.append(files[file_index])
                    doc_part.set_content_disposition("form-data", filename=file_names[file_index])
            async with self._session.post(url=full_path, data=mp, headers=headers, timeout=self._http_timeout, ssl=False) as response:
                await self._check_response_errors(response=response)
                if expect_result:
                    text = await response.text()
                    return text
                else:
                    return None
    
    async def _check_response_errors(self, response:aiohttp.ClientResponse) -> None:
        self._logger.info(f"got coord http response {response.status} {response.reason}")
        if not response.ok:
            try:
                text = await response.text()
            except Exception as ex: 
                text = f"<failed to get response text: {str(ex)}>"
            message:str = f"Got bad status code: {response.status} {response.reason}: {text}"
            self._logger.error(message)
            raise aiohttp.ClientResponseError(request_info=response.request_info, history=response.history, status=response.status, message=message)    

    async def _get_file(self, url:str) -> bytes:
        self._logger.info(f"Getting file from {url}")
        async with self._session.get(url=url, timeout=self._get_file_timeout, ssl=False) as response:
            return await response.read()
        
    async def _get_file_with_retries(self, url:str, max_retries:int|None) -> bytes:
        if max_retries is None:
            max_retries = self._max_retries
        else:
            assert max_retries >= 0
        max_attempts = max_retries + 1
        attempt = 0
        while attempt < max_attempts:
            try:
                attempt += 1
                return await self._get_file(url=url)
            except Exception as ex:
                self._logger.info(f"Attempt {attempt}/{max_attempts} of getting file at {url} failed: {ex}")
                if self._should_retry(ex):
                    if attempt >= max_attempts:
                        self._logger.error(f"Max retries reached. Raising exception. {ex}") 
                        raise 
                    else:
                        delay = self._delay_between_retries_seconds * attempt
                        self._logger.debug(f"Waiting for {delay} seconds") 
                        await asyncio.sleep(delay)    
                else:
                    raise
        assert False        


