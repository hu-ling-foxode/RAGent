from pydantic import BaseModel
from datetime import datetime

class Message(BaseModel):
  is_in_thread: bool = False
  is_image: bool = False
  message_str: str
  posted_at: datetime
  author: str
  channel_id: int
  just_msg: str
