import enum
import aiohttp
from typing import BinaryIO
from uuid import UUID
from pydantic import BaseModel
from .common import *
from .base_client import BaseClient

class SourceFile(BaseModel):
    type:FileType
    name:str
    is_temporary:bool|None = None

class GenerateRequestV4(BaseModel):
    trace_id:str
    mode:str
    user_identifier:str|None = None
    cache_force_bypass:bool|None = None
    query:str|None = None
    model_params:dict
    files:list[SourceFile]|None = None
    deadline_seconds:int|None = None
    source_files_query_id:UUID|None = None
    source_query_id:UUID|None = None
    duplicate_result_to_query_id:UUID|None = None

class GenerateRequestV3(BaseModel):
    trace_id:str
    mode:str
    query:str|None = None
    user_identifier:str|None = None
    cache_force_bypass:bool|None = None
    model_params:dict|None = None
    deadline_seconds:int|None = None
    source_files_query_id:UUID|None = None
    source_query_id:UUID|None = None
    duplicate_result_to_query_id:UUID|None = None

class GenerateResult(str, enum.Enum):
    accepted = 'accepted'
    rejected = 'rejected'

class GenerateResponse(BaseModel):
    result:GenerateResult
    query_id:UUID|None = None
    reason:str|None = None
    ready_estimation_seconds:float|None = None

class GetResultRequest(BaseModel):
    query_id:UUID
    get_image_hashes:bool|None = None

class ResultStatus(str, enum.Enum):
    ready = 'ready'
    pending = 'pending'
    unknown_query_id = 'unknown_query_id'
    cancelled = 'cancelled'

class ResultFile(BaseModel):
    type:FileType
    url:str

class ResultResultFile(ResultFile):
    hash:str|None = None

class ResultRequestFile(ResultFile):
    name:str|None = None

class GetResultResponse(BaseModel):
    status:ResultStatus
    ready_estimation_seconds:float|None = None
    results:list[ResultResultFile]|None = None
    result_json:dict|None = None
    censored:bool|None = None
    served_from_cache:bool|None = None
    # source request data
    query_id:UUID|None = None #none if unknown_query_id
    mode:str|None = None
    query:str|None = None
    request_files:list[ResultRequestFile]|None = None
    source_files_query_id:UUID|None = None
    model_params:dict|None = None

class CancelRequest(BaseModel):
    query_id:UUID

class CancelResult(str, enum.Enum):
    cancelled = 'cancelled'
    generated = 'generated'
    in_progress = 'in_progress'
    unknown_query_id = 'unknown_query_id'

class CancelResponse(BaseModel):
    result:CancelResult

class GetModeStatsRequest(BaseModel):
    mode:str

class GetModeStatsResponse(BaseModel):
    avg_queue_size:float
    avg_queue_allocated_size:float
    avg_worker_count:float


class CoordinatorClient(BaseClient):
    def __init__(
            self, 
            base_url:str, 
            api_key:str, 
            http_timeout:aiohttp.ClientTimeout|None=aiohttp.ClientTimeout(total=2, connect=2),
            get_file_timeout:aiohttp.ClientTimeout|None=aiohttp.ClientTimeout(total=10, connect=5)
        ):
        super().__init__(base_url=base_url, api_key=api_key, http_timeout=http_timeout, get_file_timeout=get_file_timeout)

    async def generate_v4(self, req:GenerateRequestV4, files:list[BinaryIO]|None = None, x_request_id:str|None=None, max_retries:int|None=None) -> GenerateResponse:
        if req.files is not None:
            file_names = [x.name for x in req.files]
        else:
            file_names = None
        res:str|None = await self._post_multipart_with_retries(path="v4/client/generate", req=req, files=files, file_names=file_names, x_request_id=x_request_id, max_retries=max_retries, expect_result=True)
        assert res is not None
        return GenerateResponse.model_validate_json(res)        

    async def generate_v3(self, req:GenerateRequestV3, x_request_id:str|None=None, max_retries:int|None=None) -> GenerateResponse:
        res:str|None = await self._post_json_with_retries("v3/client/generate", req, x_request_id=x_request_id, max_retries=max_retries, expect_result=True)
        assert res is not None
        return GenerateResponse.model_validate_json(res)

    async def get_result(self, req:GetResultRequest, x_request_id:str|None=None, max_retries:int|None=None) -> GetResultResponse:
        res:str|None = await self._post_json_with_retries("v4/client/get_result", req, x_request_id=x_request_id, max_retries=max_retries, expect_result=True)
        assert res is not None
        return GetResultResponse.model_validate_json(res)

    async def cancel(self, req:CancelRequest, x_request_id:str|None=None, max_retries:int|None=None) -> CancelResponse:
        res:str|None = await self._post_json_with_retries("v4/client/cancel", req, x_request_id=x_request_id, max_retries=max_retries, expect_result=True)
        assert res is not None
        return CancelResponse.model_validate_json(res)

    async def get_mode_stats(self, req:GetModeStatsRequest, x_request_id:str|None=None, max_retries:int|None=None) -> GetModeStatsResponse:
        res:str|None = await self._post_json_with_retries("v4/client/get_mode_stats", req, x_request_id=x_request_id, max_retries=max_retries, expect_result=True)
        assert res is not None
        return GetModeStatsResponse.model_validate_json(res)

    async def get_result_file(self, file:ResultFile, max_retries:int|None=None) -> bytes:
        return await self._get_file_with_retries(url=file.url, max_retries=max_retries)
