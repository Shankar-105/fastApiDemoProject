from fastapi import File, UploadFile, APIRouter, Depends
from uuid import uuid4
from app import oauth2
from app.services.blob_service import upload_blob
router = APIRouter()

@router.post("/upload-media")
async def upload_media(
    file:UploadFile = File(...),
    current_user = Depends(oauth2.getCurrentUser)
):
    # 'video', 'audio', 'image'
    media_type = file.content_type.split("/")[0]
    file_extension = file.filename.split(".")[-1]
    blob_name = f"{media_type}s/{uuid4()}.{file_extension}"
    content_bytes = await file.read()
    media_url = await upload_blob("chat-media", blob_name, content_bytes, file.content_type)
    return {"media_url": media_url, "type": media_type}
