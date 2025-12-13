from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import io
import urllib.parse
from processor import process_pdf

router = APIRouter()


@router.post(
    "/upload",
    summary="Загрузка PDF и получение обработанного файла",
    description="""
Загружает PDF-документ, запускает алгоритм проверки оформления
(шрифты, отступы, межстрочный интервал, выравнивание, картинки),
и возвращает исправленный PDF-файл.

**Требования:**
- Файл должен быть формата PDF
- MIME-типы: `application/pdf` или `application/x-pdf`
- Неверный формат - 400
"""
)
async def download_pdf(file: UploadFile = File(...)):


    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"Ожидается PDF файл, получено: {file.content_type}"
        )


    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Файл должен иметь расширение .pdf"
        )


    file_bytes = await file.read()


    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail="Файл не является корректным PDF-документом"
        )


    try:
        processed = process_pdf(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки PDF: {e}"
        )


    orig_name = f"processed_{file.filename}"
    encoded_name = urllib.parse.quote(orig_name)

    return StreamingResponse(
        io.BytesIO(processed),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=processed.pdf; "
                f"filename*=UTF-8''{encoded_name}"
            )
        }
    )
