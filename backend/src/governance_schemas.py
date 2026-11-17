from pydantic import BaseModel, Field
class SealInput(BaseModel):
    name:str=Field(min_length=1,max_length=60)
    trial_ids:list[int]=Field(min_length=8)
class EpochInput(BaseModel):
    epoch:int=Field(ge=0)
class RejectInput(BaseModel):
    reason:str=Field(min_length=4,max_length=300)
class RollbackInput(BaseModel):
    epoch:int=Field(ge=0)
    reason:str=Field(default='',max_length=300)
