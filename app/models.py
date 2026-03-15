from pydantic import BaseModel

class Item(BaseModel):
    name: str
    description: str = None
    price: float
    tax: float = None

class User(BaseModel):
    username: str
    email: str
    full_name: str = None
    disabled: bool = None

class Settings(BaseModel):
    display_name: str
    tags: List[str] = []
