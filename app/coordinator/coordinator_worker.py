import enum
import aiohttp
from typing import BinaryIO
from uuid import UUID, uuid4
from pydantic import BaseModel
from .common import *
from .base_client import BaseClient

class WorkerRequest(BaseModel):
    worker_id:UUID|None = None  # will be set by CoordinatorWorker during send


class GetTaskRequest(WorkerRequest):
    modes:list[str]

class GetTaskResult(str, enum.Enum):
    nothing = enum.auto()
    task = enum.auto()

class TaskFile(BaseModel):
    type:FileType
    name:str
    url:str

class GetTaskResponse(BaseModel):
    result:GetTaskResult
    query_id:UUID|None = None
    trace_id:str|None = None
    mode:str
    query:str|None = None
    files:list[TaskFile]|None = None
    model_params:dict|None = None

class ResultRequest_V3(WorkerRequest):
    query_id:UUID
    result_json:dict
    censored:bool|None = None

class ResultErrorRequest(WorkerRequest):
    query_id:UUID
    error_reason:str
    result_json:dict|None = None

class ResultFile(BaseModel):
    type:FileType
    name:str

class ResultRequest_V4(WorkerRequest):
    query_id:UUID
    files:list[ResultFile]|None
    result_json:dict|None = None
    censored:bool|None = None

class InProgressRequest(WorkerRequest):
    query_id:UUID
    result_json:dict|None = None

class GetModeStatsRequest(WorkerRequest):
    mode:str

class GetModeStatsResponse(BaseModel):
    avg_queue_size:float
    avg_queue_allocated_size:float
    avg_worker_count:float


class CoordinatorWorker(BaseClient):
    def __init__(
            self, 
            base_url:str, 
            api_key:str, 
            worker_id:UUID|None=None, 
            http_timeout:aiohttp.ClientTimeout|None=aiohttp.ClientTimeout(total=5, connect=5),
            get_file_timeout:aiohttp.ClientTimeout|None=aiohttp.ClientTimeout(total=10, connect=5)
        ):
        super().__init__(base_url=base_url, api_key=api_key, http_timeout=http_timeout, get_file_timeout=get_file_timeout)
        if worker_id is None:
            worker_id = uuid4()
        self.worker_id:UUID = worker_id
        self._logger.info(f"Using worker_id {worker_id}")

    async def get_task(self, req:GetTaskRequest, x_request_id:str|None=None, max_retries:int|None=None) -> GetTaskResponse:
        req.worker_id = self.worker_id
        res:str|None = await self._post_json_with_retries("v4/worker/get_task", req, x_request_id=x_request_id, max_retries=max_retries, expect_result=True)
        assert res is not None
        return GetTaskResponse.model_validate_json(res)

    async def result_v3(self, req:ResultRequest_V3, x_request_id:str|None=None, max_retries:int|None=None) -> None:
        req.worker_id = self.worker_id
        await self._post_json_with_retries("v3/worker/result", req, x_request_id=x_request_id, max_retries=max_retries, expect_result=False)

    async def result_v4(self, req:ResultRequest_V4, files:list[BinaryIO]|None = None, x_request_id:str|None=None, max_retries:int|None=None) -> None:
        req.worker_id = self.worker_id
        if req.files is not None:
            file_names = [x.name for x in req.files]
        else:
            file_names = None
        await self._post_multipart_with_retries(path="v4/worker/result", req=req, files=files, file_names=file_names, x_request_id=x_request_id, max_retries=max_retries, expect_result=False)

    async def result_error(self, req:ResultErrorRequest, x_request_id:str|None=None, max_retries:int|None=None) -> None:
        req.worker_id = self.worker_id
        await self._post_json_with_retries("v3/worker/result", req, x_request_id=x_request_id, max_retries=max_retries, expect_result=False)

    async def in_progress(self, req:InProgressRequest, x_request_id:str|None=None, max_retries:int|None=None) -> None:
        req.worker_id = self.worker_id
        await self._post_json_with_retries("v4/worker/in_progress", req, x_request_id=x_request_id, max_retries=max_retries, expect_result=False)

    async def get_mode_stats(self, req:GetModeStatsRequest, x_request_id:str|None=None, max_retries:int|None=None) -> GetModeStatsResponse:
        req.worker_id = self.worker_id
        res:str|None = await self._post_json_with_retries("v4/worker/get_mode_stats", req, x_request_id=x_request_id, max_retries=max_retries, expect_result=True)
        assert res is not None
        return GetModeStatsResponse.model_validate_json(res)
    
    async def get_task_file(self, file:TaskFile, max_retries:int|None=None) -> bytes:
        return await self._get_file_with_retries(url=file.url, max_retries=max_retries)