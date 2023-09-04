from sqlalchemy.orm import Session
from fastapi import Depends, FastAPI

from . import crud, schemas
from .database import Session as SessionLocal


app = FastAPI()


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/inmates/{jurisdiction}/{inmate_id}", response_model=schemas.Inmate)
async def read_inmate(
    jurisdiction: str, inmate_id: int, session: Session = Depends(get_db)
):
    return await crud.get_inmate_by_jurisdiction_and_id(
        session, jurisdiction, inmate_id
    )
